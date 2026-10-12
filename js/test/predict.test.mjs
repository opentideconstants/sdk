import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import * as sdk from '../dist/index.js';
const vectors=JSON.parse(fs.readFileSync(new URL('../../conformance/vectors/1.0/vectors.json',import.meta.url),'utf8'));
let client;
before(async()=>{assert.ok(process.env.OTC_PREDICT_NATIVE_JSON,'actual pinned vector release required');client=await sdk.OpenTideConstants.open({file:process.env.OTC_PREDICT_NATIVE_JSON});});
after(()=>client?.close());
for(const [family,op] of [['1820000','heights_at'],['BOS1101','currents'],['ACT1591','current_events']]) {
    test(`native immutable ${family}/${op}`,async()=>{
        const v=vectors.vectors.find(v=>v.id.includes(family)&&v.op===op);
        assert.ok(v,'actual vector must exist');
        const a=v.args, options={};
        for(const [k,value] of Object.entries(a)) {
            if(k==='station_id'||k==='times')continue;
            options[k.replace(/_([a-z])/g,(_,c)=>c.toUpperCase())]=k==='start'||k==='stop'?new Date(value):value;
        }
        const name=op.replace(/_([a-z])/g,(_,c)=>c.toUpperCase());
        assert.equal(typeof client[name],'function',`${name} actual SDK implementation missing`);
        const result=await (op==='heights_at'?client[name](a.station_id,a.times.map(t=>new Date(t)),options):client[name](a.station_id,options));
        const expected=v.expect.prediction;
        assert.equal(result.items.length,expected.items.length);
        for(let index=0;index<expected.items.length;index++) {
            const actual=result.items[index], row=expected.items[index];
            for(const [key,value] of Object.entries(row)) {
                if(key==='time')assert.ok(Math.abs(actual.time.getTime()-Date.parse(value))<=1000);
                else if(typeof value==='number')assert.ok(Math.abs(actual[key]-value)<= (key==='direction_deg'?0.01:1e-5),`${family} ${index} ${key}: ${actual[key]} versus ${value}`);
                else assert.deepEqual(actual[key],value);
            }
        }
    });
}

// Browser has no filesystem: authenticate and serve the same immutable input over real HTTP.
test('native browser all immutable vectors and actual Intl localization',async()=>{
    const root=fileURLToPath(new URL('../..',import.meta.url));
    const dist=process.env.OTC_BROWSER_SDK_DIR ?? path.join(root,'js/dist');
    const bytes=fs.readFileSync(path.join(root,'conformance/vectors/1.0/vectors-release.json'));
    const parsed=JSON.parse(bytes.toString('utf8'));
    const digest=b=>createHash('sha256').update(b).digest('hex');
    assert.equal(digest(bytes),vectors.release_sha256,'exact immutable input bytes');
    const date=parsed.release.datestamp,name=`OTC_${date}.json`,sha=Buffer.from(`${digest(bytes)}  ${name}\n`);
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
    const origin=`http://127.0.0.1:${server.address().port}`;
    let browser;
    try {
        browser=await chromium.launch({headless:true});
        const page=await browser.newPage();await page.goto(origin);
        const observed=await page.evaluate(async({origin,rows})=>{
            const {OpenTideConstants}=await import('/sdk/index.js');
            const client=await OpenTideConstants.open({baseUrl:origin+'/',cacheDir:'native-immutable-vector-input'});
            const results=[];
            try {
                for(const vector of rows){
                    const a=vector.args,options={};
                    for(const [key,value]of Object.entries(a)){if(key==='station_id'||key==='times')continue;options[key.replace(/_([a-z])/g,(_,c)=>c.toUpperCase())]=key==='start'||key==='stop'?new Date(value):value;}
                    const op=vector.op.replace(/_([a-z])/g,(_,c)=>c.toUpperCase());
                    try {const result=await(vector.op==='heights_at'?client.heightsAt(a.station_id,a.times.map(t=>new Date(t)),options):client[op](a.station_id,options));
                        const metadata=Object.fromEntries(['station_id','timezone','method','set_id','convention_id','astro_table_id','reference_station_id','reference_bin','datum','datum_name','datum_kind','datum_uncertainty_m','bin_number','omitted_event_types','tz','tz_version','release','algorithm'].map(k=>[k,result[k]??null]));
                        results.push({id:vector.id,prediction:{...metadata,items:result.items.map(item=>({...item,time:item.time.toISOString().replace('.000Z','Z')}))}});
                    } catch(error){results.push({id:vector.id,error:error.code??String(error)});}
                }
                const native=await client.heightsAt('OTC-V-NOAA-1820000',[new Date('2010-03-01T00:00:00Z')]);
                const local=native.toLocal('UTC');
                return {results,local:local.items[0].local_time,offset:local.items[0].utc_offset_s,original:native.items[0].local_time,version:local.tz_version,cache:await caches.keys()};
            } finally {client.close();}
        },{origin,rows:vectors.vectors});
        for(let i=0;i<vectors.vectors.length;i++) {
            const vector=vectors.vectors[i],actual=observed.results[i],expected=vector.expect.prediction;
            assert.equal(actual.error,undefined,vector.id);
            for(const [key,value]of Object.entries(expected))if(key!=='items')assert.deepEqual(actual.prediction[key],value,`${vector.id} ${key}`);
            assert.equal(actual.prediction.items.length,expected.items.length,vector.id);
            for(let j=0;j<expected.items.length;j++)for(const [key,value]of Object.entries(expected.items[j])){
                const got=actual.prediction.items[j][key];
                if(key==='time')assert.ok(Math.abs(Date.parse(got)-Date.parse(value))<=1000,vector.id);
                else if(typeof value==='number')assert.ok(Math.abs(got-value)<=(key==='direction_deg'?0.01:1e-5),`${vector.id} ${j} ${key}`);
                else assert.deepEqual(got,value,`${vector.id} ${j} ${key}`);
            }
        }
        assert.equal(observed.local,'2010-03-01T00:00:00+00:00');assert.equal(observed.offset,0);assert.equal(observed.original,null);assert.equal(observed.version,null);
        assert.ok(observed.cache.includes('opentideconstants-v1:native-immutable-vector-input'));
        console.log('actual Chromium: all60 immutable vector predictions and native Intl GREEN');
    } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
});

test('native closed precedence, repeated UTC instants and immutable local values',async()=>{
    const local=await sdk.OpenTideConstants.open({file:process.env.OTC_PREDICT_NATIVE_JSON});
    const time=new Date('2010-03-01T00:00:00.999Z');
    const result=await local.heightsAt('OTC-V-NOAA-1820000',[time,time]);
    assert.equal(result.items.length,2);assert.equal(result.items[0].time.toISOString(),'2010-03-01T00:00:00.000Z');
    assert.equal(result.items[0].height_m,result.items[1].height_m);
    assert.throws(()=>{result.items[0].height_m=4;},TypeError);
    assert.throws(()=>{result.items.push(result.items[0]);},TypeError);
    assert.throws(()=>result.items[0].time.setTime(0),TypeError);
    const converted=result.toLocal('UTC');assert.equal(converted.items[0].local_time,'2010-03-01T00:00:00+00:00');assert.equal(result.items[0].local_time,null);
    assert.throws(()=>result.toLocal('posix/UTC'),e=>e.code==='unknown_time_zone');
    const release=local.release;local.close();
    for(const op of ['heights','extremes','currents','currentEvents'])await assert.rejects(release[op]('OTC-V-NOAA-1820000',{start:new Date(NaN),stop:new Date(NaN)}),e=>e.code==='io');
    await assert.rejects(release.heightsAt('OTC-V-NOAA-1820000',null),e=>e.code==='io');
    await assert.rejects(release.astroTable(),e=>e.code==='io');
});
