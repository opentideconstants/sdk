import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import * as sdk from '../dist/index.js';
import {makeRunner} from '../../conformance/runners/node/ops.mjs';
import {materialize_typed_model} from '../dist/canonical.js';

const start=new Date(1798761600*1000),stop=new Date(1798848000*1000);
const times=[1798761600,1798783200,1798804800].map(t=>new Date(t*1000));
// CI uses the committed native vector release. The accepted full-population
// proof remains available locally with OTC_UNITS_NATIVE_JSON (JSONL + metadata).
const actualRelease=process.env.OTC_UNITS_NATIVE_JSON;
let file=actualRelease,directory;
before(()=>{
    if(actualRelease)return;
    directory=fs.mkdtempSync(path.join(os.tmpdir(),'otc-units-'));
    const {stations,...metadata}=JSON.parse(fs.readFileSync(new URL('../../conformance/vectors/1.0/vectors-release.json',import.meta.url),'utf8'));
    const stem=`OTC_${metadata.release.datestamp}`;
    file=path.join(directory,`${stem}.jsonl`);
    fs.writeFileSync(file,stations.map(station=>JSON.stringify(station)+'\n').join(''));
    fs.writeFileSync(path.join(directory,`${stem}.meta.json`),JSON.stringify(metadata));
});
after(()=>{if(directory)fs.rmSync(directory,{recursive:true,force:true});});

const cases=actualRelease?[
    ['heights','OTC-e813b80c',{start,stop,stepS:600,datum:'zero'},'feet',{height:'height_m'}],
    ['heightsAt','OTC-e813b80c',{datum:'zero'},'feet',{height:'height_m'}],
    ['extremes','OTC-e813b80c',{start,stop,datum:'zero'},'feet',{height:'height_m'}],
    ['extremes','OTC-0031a9c4',{start,stop},'feet',{height:'height_m'}],
    ['currents','OTC-00bdf4b5',{start,stop,stepS:600,binNumber:14},'knots',{velocity_major:'velocity_major_ms',velocity_minor:'velocity_minor_ms',speed:'speed_ms'}],
    ['currentEvents','OTC-00bdf4b5',{start,stop,binNumber:14},'knots',{velocity:'velocity_ms'}],
]:[
    ['heights','OTC-V-NOAA-1820000',{start,stop,stepS:600,datum:'zero'},'feet',{height:'height_m'}],
    ['heightsAt','OTC-V-NOAA-1820000',{datum:'zero'},'feet',{height:'height_m'}],
    ['extremes','OTC-V-NOAA-1820000',{start,stop,datum:'zero'},'feet',{height:'height_m'}],
    ['currents','OTC-V-NOAA-ACT1616',{start,stop,stepS:600,binNumber:1},'knots',{velocity_major:'velocity_major_ms',velocity_minor:'velocity_minor_ms',speed:'speed_ms'}],
    ['currentEvents','OTC-V-NOAA-ACT1591',{start,stop,binNumber:1},'knots',{velocity:'velocity_ms'}],
];
const predict=(target,method,station,options)=>method==='heightsAt'?target.heightsAt(station,times,options):target[method](station,options);

for(const mode of ['eager','stream'])test(`actual units, defaults, forwarding and localization (${mode})`,async()=>{
    const client=await sdk.OpenTideConstants.open({file,mode});
    try {
        for(const [method,station,options,units,mapping] of cases){
            const defaultUnits=units==='feet'?'meters':'m/s',divisor=units==='feet'?0.3048:1852/3600;
            const si=await predict(client,method,station,options);
            const explicitSI=await predict(client.release,method,station,{...options,units:defaultUnits});
            assert.deepEqual(explicitSI,si);
            assert.equal(si.units,defaultUnits);
            const selected=await predict(client,method,station,{...options,units});
            const direct=await predict(client.release,method,station,{...options,units});
            assert.deepEqual(direct,selected);
            assert.equal(selected.units,units);
            assert.ok(selected.items.length>0);
            if(station==='OTC-0031a9c4')assert.equal(selected.reference_station_id,'OTC-d77f0463');
            const localized=selected.toLocal('America/New_York');
            assert.equal(localized.units,units);
            selected.items.forEach((item,i)=>{
                assert.equal(item.units,units);
                assert.equal(si.items[i].units,defaultUnits);
                const {units:ignored,...siFields}=si.items[i];
                const {units:selectedUnits,...selectedFields}=item;
                assert.deepEqual(selectedFields,siFields);
                for(const [value,siField] of Object.entries(mapping)){
                    assert.equal(item[value],item[siField]/divisor);
                    assert.equal(si.items[i][value],si.items[i][siField]);
                    assert.equal(localized.items[i][value],item[value]);
                    assert.throws(()=>{item[value]=0;},TypeError);
                }
                assert.equal(localized.items[i].units,units);
                const legacy=new item.constructor(siFields);
                assert.equal(legacy.units,defaultUnits);
                const copy=new item.constructor({...item});
                for(const value of Object.keys(mapping))assert.equal(copy[value],item[value]);
                const model_type=item.constructor.name;
                const native=materialize_typed_model({}, {model_type,fields:[],native_result_fields:{model_type,fields:{...item}}}, {}, model_type).model;
                assert.equal(native.units,units);
                for(const value of Object.keys(mapping))assert.equal(native[value],item[value]);
            });
            const {units:ignored,...legacyFields}=si;
            assert.equal(new si.constructor(legacyFields).units,defaultUnits);
            const copy=new selected.constructor({...selected});
            assert.equal(copy.units,units);
            const model_type=selected.constructor.name;
            const native=materialize_typed_model({}, {model_type,fields:[],native_result_fields:{model_type,fields:{...selected}}}, {}, model_type).model;
            assert.deepEqual(native,selected);
            await assert.rejects(predict(client,method,station,{...options,units:'furlongs'}),e=>e.code==='invalid_argument');
        }
    } finally {client.close();}
});

test('runner exposes selected fields only for explicit units and retains them through to_local',async()=>{
    const runner=makeRunner(sdk);
    const opened=await runner.handle({op:'open',args:{file}});
    assert.equal(opened.ok,true);
    try {
        const args={station_id:cases[0][1],start:start.toISOString(),stop:stop.toISOString(),datum:'zero'};
        for(const explicit of [true,false]){
            const reply=await runner.handle({op:'heights',args:explicit?{...args,units:'feet'}:args});
            assert.equal(reply.ok,true);
            assert.equal(Object.hasOwn(reply.result.prediction,'units'),explicit);
            assert.equal(Object.hasOwn(reply.result.prediction.items[0],'units'),explicit);
            assert.equal(Object.hasOwn(reply.result.prediction.items[0],'height'),explicit);
            const local=await runner.handle({op:'to_local',args:{tz:'America/New_York'}});
            assert.equal(local.ok,true);
            assert.equal(Object.hasOwn(local.result.prediction,'units'),explicit);
            assert.equal(Object.hasOwn(local.result.prediction.items[0],'height'),explicit);
        }
    } finally {await runner.shutdown();}
});
