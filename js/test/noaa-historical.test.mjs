import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import * as sdk from '../dist/index.js';

const input=process.env.OTC_HISTORY_NATIVE_JSON;
const jsonl=process.env.OTC_HISTORY_NATIVE_JSONL;
const reference=process.env.OTC_HISTORY_REFERENCE_REPORT;
const start=new Date('2026-10-11T00:00:00Z'),stop=new Date('2026-10-12T00:00:00Z');
const rows=result=>result.items.map(e=>({time:e.time.toISOString(),type:e.type,height_m:e.height_m}));
function compareEvents(actual,expected) {
    assert.equal(actual.length,expected.length);
    for(let i=0;i<actual.length;i++) {assert.equal(actual[i].time, new Date(expected[i].time).toISOString());assert.equal(actual[i].type,expected[i].type);assert.ok(Math.abs(actual[i].height_m-expected[i].height_m)<1e-10);}
}

test('actual historical Chromium HTTP/CacheStorage arithmetic, metadata and strict discovery',async()=>{
    const browserInput=process.env.OTC_HISTORY_BROWSER_JSON;
    assert.ok(browserInput&&reference,'lossless actual six-row H4 browser input and pinned Python report required');
    const bytes=fs.readFileSync(browserInput),parsed=JSON.parse(bytes.toString('utf8'));
    const expected=JSON.parse(fs.readFileSync(reference,'utf8'));
    const digest=value=>createHash('sha256').update(value).digest('hex');
    const date=parsed.release.datestamp,name=`OTC_${date}.json`,sha=Buffer.from(`${digest(bytes)}  ${name}\n`);
    const dist=fileURLToPath(new URL('../dist/',import.meta.url));
    const server=createServer((request,response)=>{
        const url=new URL(request.url,'http://localhost');
        if(url.pathname==='/'){response.setHeader('content-type','text/html');response.end('<!doctype html>');return;}
        if(url.pathname.startsWith('/sdk/')){response.setHeader('content-type','text/javascript');response.end(fs.readFileSync(path.join(dist,path.normalize(url.pathname.slice(5)))));return;}
        if(url.pathname.endsWith('/'+name)){response.end(bytes);return;}
        if(url.pathname.endsWith(`/OTC_${date}.sha256`)){response.end(sha);return;}
        if(url.pathname.endsWith('/OTC_latest-f1.json')||url.pathname.endsWith('/OTC_latest.json')){response.end(JSON.stringify({...parsed.release,format_version:parsed.format_version,files:[{name,sha256:digest(bytes),size:bytes.length},{name:`OTC_${date}.sha256`,sha256:digest(sha),size:sha.length}]}));return;}
        response.statusCode=404;response.end();
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    let browser;
    try {
        browser=await chromium.launch({headless:true});
        const page=await browser.newPage(),origin=`http://127.0.0.1:${server.address().port}`;await page.goto(origin);
        const actual=await page.evaluate(async({origin,controls})=>{
            const {OpenTideConstants}=await import('/sdk/index.js');
            const options={baseUrl:origin+'/',cacheDir:'native-historical-value'};
            const start=new Date('2026-10-11T00:00:00Z'),stop=new Date('2026-10-12T00:00:00Z');
            const client=await OpenTideConstants.open(options),values=[];
            try {
                for(const id of ['OTC-28c56e20','OTC-541f1a73',...controls]) {
                    const value=await client.extremes(id,{start,stop,datum:'chart'});
                    const own=client.requireStation(id).subordinateOffsets;
                    const explicit=own?await client.extremes(id,{start,stop,datum:'chart',offsetId:own.offset_id}):null;
                    const events=result=>result.items.map(e=>({time:e.time.toISOString(),type:e.type,height_m:e.height_m}));
                    values.push({id,events:events(value),explicit:explicit?events(explicit):null,metadata:Object.fromEntries(['set_id','offset_id','offset_source','offset_source_version','historical_offsets','current_accuracy','current_validity','reference_2020_equivalence','reference_set_id'].map(k=>[k,value[k]]))});
                }
            } finally {client.close();}
            const strict=await OpenTideConstants.open({...options,historicalOffsetsPolicy:'exclude'}),refusals=[];
            try {for(const id of ['OTC-28c56e20','OTC-541f1a73']) {
                for(const flags of [{},{includeFlagged:true},{includeFallback:true},{includeFlagged:true,includeFallback:true}])refusals.push(!strict.stations(flags).some(s=>s.station_id===id));
                for(const args of [{start,stop},{start,stop,offsetId:strict.requireStation(id).subordinateOffsets.offset_id}]) {
                    try {await strict.extremes(id,args);refusals.push(false);}catch(error){refusals.push(error.code==='historical_offsets_excluded');}
                }
            }} finally {strict.close();}
            return {values,refusals,cache:await caches.keys()};
        },{origin,controls:expected.unchanged_controls.filter(c=>c.mode==='eager').map(c=>c.station_id)});
        for(const value of actual.values) {
            const id=value.id;
            if(id==='OTC-28c56e20'||id==='OTC-541f1a73') {
                compareEvents(value.events,value.explicit);
                for(const cell of expected.numeric_cells.filter(c=>c.mode==='eager'&&c.station_id===id))compareEvents([value.events.find(e=>e.type===cell.kind)],[{time:cell.time,type:cell.kind,height_m:cell.height_m}]);
                assert.equal(value.metadata.set_id,null);assert.equal(value.metadata.offset_source,'noaa');assert.equal(value.metadata.offset_source_version,'annual-tide-tables-2020');
                assert.equal(value.metadata.historical_offsets,true);assert.equal(value.metadata.current_accuracy,'unverified');assert.equal(value.metadata.current_validity,'unestablished');assert.equal(value.metadata.reference_2020_equivalence,'disagrees');
                assert.ok(value.metadata.offset_id);assert.ok(value.metadata.reference_set_id);
            } else compareEvents(value.events,expected.unchanged_controls.find(c=>c.mode==='eager'&&c.station_id===id).events);
        }
        assert.equal(actual.refusals.length,12);assert.ok(actual.refusals.every(Boolean));assert.ok(actual.cache.includes('opentideconstants-v1:native-historical-value'));
        console.log('actual Chromium H4: two defaults, four published arithmetic cells, three unchanged contexts, strict all4 flags GREEN');
    } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
});
for(const mode of ['eager','stream']) {
    test(`actual historical ${mode} two defaults/arithmetic/three contexts/strict labels`,async()=>{
        assert.ok(input&&jsonl&&reference,'actual historical files and pinned Python report required');
        const expected=JSON.parse(fs.readFileSync(reference,'utf8'));
        const client=await sdk.OpenTideConstants.open({file:mode==='stream'?jsonl:input,mode});
        try {
            for(const id of ['OTC-28c56e20','OTC-541f1a73']) {
                const source=client.requireStation(id).subordinateOffsets;
                const result=await client.extremes(id,{start,stop,datum:'chart'});
                const explicit=await client.extremes(id,{start,stop,datum:'chart',offsetId:source.offset_id});
                assert.deepEqual(rows(result),rows(explicit));
                assert.equal(result.offset_id,source.offset_id);assert.equal(result.set_id,null);
                assert.equal(result.offset_source,'noaa');assert.equal(result.offset_source_version,'annual-tide-tables-2020');
                assert.equal(result.historical_offsets,true);assert.equal(result.current_accuracy,'unverified');
                assert.equal(result.current_validity,'unestablished');assert.equal(result.reference_2020_equivalence,'disagrees');
                assert.ok(result.reference_set_id.startsWith(source.reference_station_id+'/'));
                for(const cell of expected.numeric_cells.filter(c=>c.mode==='eager'&&c.station_id===id)) {
                    const actual=rows(result).find(e=>e.type===cell.kind);
                    assert.equal(actual.time,new Date(cell.time).toISOString());assert.ok(Math.abs(actual.height_m-cell.height_m)<1e-10);
                }
                await assert.rejects(client.heights(id,{start,stop}),e=>e.code==='extremes_only');
                await assert.rejects(client.heightsAt(id,[start]),e=>e.code==='extremes_only');
            }
            for(const control of expected.unchanged_controls.filter(c=>c.mode==='eager'))compareEvents(rows(await client.extremes(control.station_id,{start,stop,datum:'chart'})),control.events);
        } finally {client.close();}
        const strict=await sdk.OpenTideConstants.open({file:mode==='stream'?jsonl:input,mode,historicalOffsetsPolicy:'exclude'});
        try {for(const id of ['OTC-28c56e20','OTC-541f1a73']) {
            assert.ok(strict.station(id));
            for(const flags of [{},{includeFlagged:true},{includeFallback:true},{includeFlagged:true,includeFallback:true}])assert.equal(strict.stations(flags).some(s=>s.station_id===id),false);
            await assert.rejects(strict.extremes(id,{start,stop}),e=>e.code==='historical_offsets_excluded');
            await assert.rejects(strict.extremes(id,{start,stop,offsetId:strict.requireStation(id).subordinateOffsets.offset_id}),e=>e.code==='historical_offsets_excluded');
        }} finally {strict.close();}
    });
}

test('actual historical own QC, parent QC, existing NC licence and table negative controls',async()=>{
    const small=process.env.OTC_HISTORY_BROWSER_JSON;
    assert.ok(small,'lossless actual six-row H4 input required');
    const base=JSON.parse(fs.readFileSync(small,'utf8')),id='OTC-28c56e20';
    const nc=base.licences.find(l=>l.commercial_use===false);
    assert.ok(nc,'an original declared noncommercial licence must exist');
    const directory=fs.mkdtempSync(path.join(os.tmpdir(),'otc-historical-native-'));
    const controls=[
        {name:'own-qc',edit:(document,station)=>{station.subordinate_offsets.qc_status='no_constants';},loadCode:'invalid_release'},
        {name:'parent-qc',edit:(document,station)=>{const parent=document.stations.find(s=>s.station_id===station.subordinate_offsets.reference_station_id);parent.constant_sets.find(c=>c.source==='noaa').qc_status='flagged';},code:'no_constants'},
        {name:'own-nc',edit:(document,station)=>{station.subordinate_offsets.licence_id=nc.licence_id;},open:{commercialOnly:true},code:'reference_unavailable'},
        {name:'table-absent',edit:(document,station)=>{const parent=document.stations.find(s=>s.station_id===station.subordinate_offsets.reference_station_id),set=parent.constant_sets.find(c=>c.source==='noaa');document.conventions.find(c=>c.convention_id===set.convention_id).astro_table_id='';},code:'no_astro_table'}
    ];
    try {
        for(const control of controls) {
            const document=structuredClone(base),station=document.stations.find(s=>s.station_id===id);
            control.edit(document,station);
            const file=path.join(directory,'OTC_20261011.json');fs.writeFileSync(file,JSON.stringify(document));
            if(control.loadCode){await assert.rejects(sdk.OpenTideConstants.open({file}),e=>e.code===control.loadCode);continue;}
            const client=await sdk.OpenTideConstants.open({file,...control.open});
            try {
                assert.ok(client.station(id),'raw original station stays accessible');
                for(const flags of [{},{includeFlagged:true},{includeFallback:true},{includeFlagged:true,includeFallback:true}])assert.equal(client.stations(flags).some(s=>s.station_id===id),false,control.name);
                for(const args of [{start,stop},{start,stop,offsetId:station.subordinate_offsets.offset_id}])await assert.rejects(client.extremes(id,args),e=>e.code===control.code,control.name);
            } finally {client.close();}
        }
        console.log('actual H4 scratch controls: own-QC malformed refusal, parent-QC/NC/table admission failures GREEN; original source bytes unchanged');
    } finally {fs.rmSync(directory,{recursive:true,force:true});}
});
