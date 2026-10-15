import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {spawnSync} from 'node:child_process';
import * as sdk from '../dist/index.js';
const vectors=JSON.parse(fs.readFileSync(new URL('../../conformance/vectors/1.0/vectors.json',import.meta.url),'utf8'));
let client;
before(async()=>{assert.ok(process.env.OTC_PREDICT_NATIVE_JSON,'actual pinned vector release required');client=await sdk.OpenTideConstants.open({file:process.env.OTC_PREDICT_NATIVE_JSON});});
after(()=>client?.close());
test('native reader defers heavy engine until first actual prediction',()=>{
    const root=fileURLToPath(new URL('../..',import.meta.url));
    const trace=messages=>spawnSync(process.execPath,['conformance/runners/node/runner.mjs'],{
        cwd:root,env:{...process.env,NODE_DEBUG:'esm'},input:messages.length?messages.map(m=>JSON.stringify(m)).join('\n')+'\n':'',encoding:'utf8',maxBuffer:16*1024*1024
    });
    const loaded=run=>/\/predict\/(engine|harmonic)\.js/.test(run.stderr);
    const empty=trace([]);assert.equal(empty.status,0);assert.equal(loaded(empty),false,'reader import must not load heavy prediction kernel');
    const vector=vectors.vectors.find(v=>v.id.includes('1820000')&&v.op==='heights_at');
    const open={op:'open',args:{file:process.env.OTC_PREDICT_NATIVE_JSON}};
    const metadata=trace([open,{op:'datums',args:{station_id:vector.args.station_id}},{op:'ranges',args:{station_id:vector.args.station_id}}]);
    assert.equal(metadata.status,0);assert.equal(loaded(metadata),false,'synchronous metadata must not load heavy prediction kernel');
    assert.ok(metadata.stdout.trim().split('\n').slice(1).map(JSON.parse).every(r=>r.ok));
    const first=trace([open,{op:vector.op,args:vector.args}]);
    assert.equal(first.status,0);assert.equal(loaded(first),true,'actual first prediction must load native engine');
    const reply=JSON.parse(first.stdout.trim().split('\n').at(-1));assert.equal(reply.ok,true);assert.equal(reply.result.prediction.items.length,vector.expect.prediction.items.length);
});
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
            const heavyLoaded=()=>performance.getEntriesByType('resource').some(entry=>/\/predict\/(engine|harmonic)\.js/.test(entry.name));
            const beforePrediction=heavyLoaded();
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
                return {results,beforePrediction,afterPrediction:heavyLoaded(),local:local.items[0].local_time,offset:local.items[0].utc_offset_s,original:native.items[0].local_time,version:local.tz_version,cache:await caches.keys()};
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
        assert.equal(observed.beforePrediction,false,'browser reader must defer heavy native kernel');assert.equal(observed.afterPrediction,true,'browser first actual prediction must load native kernel');
        assert.ok(observed.cache.includes('opentideconstants-v1:native-immutable-vector-input'));
        console.log('actual Chromium: all60 immutable vector predictions and native Intl GREEN');
    } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
});

// This case needs the private lossless H4 JSON/JSONL/META fixture; without OTC_BROWSER_CACHE_NATIVE_DIR or
// OTC_HISTORY_BROWSER_JSON it is skipped and says so.
const browserCacheFixture=process.env.OTC_BROWSER_CACHE_NATIVE_DIR??(process.env.OTC_HISTORY_BROWSER_JSON?path.dirname(process.env.OTC_HISTORY_BROWSER_JSON):null);
test('native browser cache prefetch reads only the selected format',{skip:browserCacheFixture?false:'OTC_BROWSER_CACHE_NATIVE_DIR (or OTC_HISTORY_BROWSER_JSON) is not set: the lossless actual H4 fixture is private'},async()=>{
    const fixture=browserCacheFixture;
    const root=fileURLToPath(new URL('../..',import.meta.url)),dist=process.env.OTC_BROWSER_SDK_DIR??path.join(root,'js/dist');
    const parsed=JSON.parse(fs.readFileSync(path.join(fixture,'OTC_20261011.json'),'utf8'));
    const date=parsed.release.datestamp,stem=`OTC_${date}`,digest=b=>createHash('sha256').update(b).digest('hex');
    const contents=Object.fromEntries(['json','jsonl','meta.json'].map(ext=>[`${stem}.${ext}`,fs.readFileSync(path.join(fixture,`${stem}.${ext}`))]));
    contents[`${stem}.sha256`]=Buffer.from(Object.entries(contents).map(([name,bytes])=>`${digest(bytes)}  ${name}\n`).join(''));
    const files=Object.entries(contents).map(([name,bytes])=>({name,sha256:digest(bytes),size:bytes.length}));
    const server=createServer((request,response)=>{
        const pathname=new URL(request.url,'http://localhost').pathname;
        if(pathname==='/'){response.setHeader('content-type','text/html');response.end('<!doctype html>');return;}
        if(pathname.startsWith('/sdk/')){response.setHeader('content-type','text/javascript');response.end(fs.readFileSync(path.join(dist,path.normalize(pathname.slice(5)))));return;}
        const name=path.basename(pathname);
        if(name==='OTC_latest-f1.json'||name==='OTC_latest.json'){response.end(JSON.stringify({...parsed.release,format_version:parsed.format_version,files}));return;}
        if(contents[name]){response.end(contents[name]);return;}
        response.statusCode=404;response.end();
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    let browser;
    try {
        browser=await chromium.launch({headless:true});
        const page=await browser.newPage(),origin=`http://127.0.0.1:${server.address().port}`;await page.goto(origin);
        const observed=await page.evaluate(async({origin,date,stem,originals,targets})=>{
            const {OpenTideConstants}=await import('/sdk/index.js');
            const options={baseUrl:origin+'/',cacheDir:'native-cache-prefetch',verifyOnOpen:false};
            const offline={...options,release:date,offline:true};
            const key=name=>`https://opentideconstants-cache.invalid/v1/releases/${date}/${name}`;
            const cache=await caches.open('opentideconstants-v1:'+options.cacheDir);
            const predictions=async client=>{
                const results=[];
                for(const id of ['OTC-a6c00a3f','OTC-28c56e20','OTC-541f1a73']) {
                    const value=await client.extremes(id,{start:new Date('2026-10-11T00:00:00Z'),stop:new Date('2026-10-12T00:00:00Z'),datum:'chart'});
                    results.push({id,items:value.items.map(item=>({...item,time:item.time.toISOString()})),offset_id:value.offset_id??null});
                }
                return results;
            };
            const eager=await OpenTideConstants.open({...options,mode:'eager'});
            const expected=await predictions(eager),expectedFiles=eager.release.files;eager.close();
            const warmed=await OpenTideConstants.open({...options,mode:'stream'});warmed.close();
            const inventory=async()=>(await Promise.all((await cache.keys()).filter(request=>request.url.includes(`/releases/${date}/`)&&!request.url.endsWith('/index-v1.json')).map(async request=>{
                const bytes=await(await cache.match(request)).arrayBuffer();
                const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
                return {name:request.url.split('/').at(-1),size:bytes.byteLength,sha256:sha};
            }))).sort((a,b)=>a.name.localeCompare(b.name));
            const before=await inventory(),reads=[],responseKeys=new WeakMap();
            const originalMatch=Cache.prototype.match,originalArrayBuffer=Response.prototype.arrayBuffer;
            Cache.prototype.match=async function(request,...args){const response=await originalMatch.call(this,request,...args);if(response)responseKeys.set(response,typeof request==='string'?request:request.url);return response;};
            Response.prototype.arrayBuffer=async function(...args){const bytes=await originalArrayBuffer.apply(this,args);const url=responseKeys.get(this);if(url)reads.push({name:url.split('/').at(-1),size:bytes.byteLength});return bytes;};
            const capture=async mode=>{const offset=reads.length,client=await OpenTideConstants.open({...offline,mode});return {client,offset};};
            const controls={};
            let actual,actualFiles,streamReads;
            try {
                const opened=await capture('stream'),client=opened.client;
                actual=await predictions(client);actualFiles=client.release.files;
                controls.raw=targets.every(target=>JSON.stringify(client.requireStation(target.station_id).raw)===JSON.stringify(target));
                controls.ownOffsets=['OTC-28c56e20','OTC-541f1a73'].every(id=>client.requireStation(id).subordinateOffsets.offset_id===targets.find(t=>t.station_id===id).subordinate_offsets.offset_id);
                controls.labels=['OTC-28c56e20','OTC-541f1a73'].every(id=>client.requireStation(id).subordinateOffsets.vintage.current_accuracy==='unverified');
                streamReads=reads.slice(opened.offset);client.close();
                try{client.stations();controls.close=false;}catch(error){controls.close=error.code==='io';}
                const eagerOpen=await capture('eager');controls.eager=JSON.stringify(await predictions(eagerOpen.client))===JSON.stringify(expected);eagerOpen.client.close();
                controls.eagerReads=reads.slice(eagerOpen.offset);
                const index=JSON.parse(await(await cache.match(key('index-v1.json'))).text());delete index.discovery_index_version;
                await cache.put(key('index-v1.json'),new Response(JSON.stringify(index)));
                const stale=await capture('stream');controls.stale=JSON.stringify(await predictions(stale.client))===JSON.stringify(expected);stale.client.close();
                await cache.delete(key(`${stem}.json`));
                const fallback=await capture('eager');controls.fallback=JSON.stringify(await predictions(fallback.client))===JSON.stringify(expected);fallback.client.close();
                controls.fallbackReads=reads.slice(fallback.offset);
                await cache.put(key(`${stem}.json`),new Response(new Uint8Array(originals[`${stem}.json`])));
                const verified=await OpenTideConstants.open({...offline,mode:'stream'}),offset=reads.length;controls.verify=await verified.verify();verified.close();controls.verifyReads=reads.slice(offset);
            } finally {Cache.prototype.match=originalMatch;Response.prototype.arrayBuffer=originalArrayBuffer;}
            return {before,after:await inventory(),expected,actual,expectedFiles,actualFiles,streamReads,controls};
        },{origin,date,stem,originals:Object.fromEntries(Object.entries(contents).map(([name,bytes])=>[name,[...bytes]])),targets:parsed.stations});
        if(process.env.OTC_BROWSER_CACHE_PROOF)fs.writeFileSync(process.env.OTC_BROWSER_CACHE_PROOF,JSON.stringify({fixture,files,...observed},null,2)+'\n');
        assert.deepEqual(observed.actual,observed.expected,'three actual predictions preserve values');
        assert.deepEqual(observed.actualFiles,observed.expectedFiles.filter(f=>f.name!==`${stem}.sha256`),'cached provenance retains verified formats');
        assert.deepEqual(observed.after,observed.before,'every original cache body remains unchanged');
        for(const name of ['raw','ownOffsets','labels','close','eager','stale','fallback','verify'])assert.equal(observed.controls[name],true,name);
        assert.ok(observed.controls.verifyReads.some(r=>r.name===`${stem}.json`),'explicit verification still hashes unused cached formats');
        console.log(JSON.stringify({streamReads:observed.streamReads,eagerReads:observed.controls.eagerReads,fallbackReads:observed.controls.fallbackReads,predictionStations:observed.actual.map(r=>r.id),originalsRetained:observed.after.length}));
        assert.deepEqual(observed.streamReads.filter(r=>![`${stem}.meta.json`,`${stem}.jsonl`,'index-v1.json','.verified'].includes(r.name)),[],'stream must not materialize unused cache bodies');
        assert.deepEqual(observed.controls.eagerReads.filter(r=>![`${stem}.json`,'.verified'].includes(r.name)),[],'eager must prefer JSON without reading sibling formats');
        assert.deepEqual(observed.controls.fallbackReads.filter(r=>![`${stem}.meta.json`,`${stem}.jsonl`,'.verified'].includes(r.name)),[],'eager JSONL fallback must not read unused bodies');
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
