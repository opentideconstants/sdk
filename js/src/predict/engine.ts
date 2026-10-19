import * as X from '../errors.js';
import {Station,type Release,type ConstantSet,predictionStation as stationFor,predictionOptions as options,predictionChosen as chosen,predictionAstroTable,requireHistoricalTableCompatibility} from '../release.js';
import {arr,num,obj,str,isObject,type JsonObject} from '../json.js';
import {AstroTable,instant,utc,angle} from './astro.js';
import {Sum,events,unroundedEvents,RAD,type Event} from './harmonic.js';
import {HeightPoint,Extreme,CurrentPoint,CurrentEvent,HeightSeries,ExtremeList,CurrentSeries,CurrentEventList} from './results.js';
import type {ExtremeType,CurrentEventType,PredictionMethod} from '../types.js';
import {requireHistoricalOffset} from '../historical-offsets.js';

export interface HeightOptions {datum?:string|null;setId?:string|null;offsetId?:string|null;}
export interface HeightWindowOptions extends HeightOptions {start:Date;stop:Date;stepS?:number;}
export interface CurrentOptions {binNumber?:number|null;setId?:string|null;}
export interface CurrentWindowOptions extends CurrentOptions {start:Date;stop:Date;stepS?:number;}
export interface DatumOptions {setId?:string|null;allSets?:boolean;}
export interface RangeOptions {setId?:string|null;}
/** @internal Borrowed, already selected native prediction context. */
export interface Context {
    station:Station;constants:ConstantSet;table:AstroTable;method:PredictionMethod;
    reference:Station|null;referenceBin:number|null;binNumber:number|null;offsets:JsonObject|null;
    total:Sum;minor:Sum|null;currentBin:JsonObject|null;sigma:number;
    datumName:string|null;datumKind:string|null;datumUncertainty:number|null;omitted:readonly CurrentEventType[]|null;
}
const objects=(o:JsonObject|null,key:string)=>arr(o,key).filter(isObject);
export function astroTable(release:Release,id:string|null=null):AstroTable|null {return predictionAstroTable(release,id);}
/** @internal */
export function contextFor(station:Station,constants:ConstantSet,table:AstroTable):Context {
    return {station,constants,table,method:'harmonic',reference:null,referenceBin:null,binNumber:null,offsets:null,
        total:new Sum(table,[]),minor:null,currentBin:null,sigma:1,datumName:null,datumKind:null,datumUncertainty:null,omitted:null};
}
/** @internal */
export function window(start:Date,stop:Date,step?:number):readonly[number,number] {
    const first=instant(start),last=instant(stop);if(first>last)throw new X.InvalidArgumentError('start must not be after stop');
    if(step!==undefined&&(typeof step!=='number'||!Number.isInteger(step)||step<=0))throw new X.InvalidArgumentError('stepS must be a positive integer');return [first,last];
}
function tableFor(release:Release,constants:ConstantSet):AstroTable {
    const convention=constants.convention;
    if(convention.v0_model!=='schureman_tcd'||convention.nodal_handling!=='f_u_at_prediction')throw new X.UnsupportedConventionError(`unsupported convention ${convention.convention_id}`);
    const id=str(convention.raw,'astro_table_id')??'',table=astroTable(release,id);
    if(!table)throw new X.NoAstroTableError(`release ${release.datestamp} has no astro table "${id}" for convention "${convention.convention_id}". Format 1.0 requires astro_tables when a convention uses f_u_at_prediction (since the schema revision of site PR #45); this file was written before that revision or is invalid.`);return table;
}
function unavailable(missing:string):never {throw new X.DatumUnavailableError(`datum is missing ${missing}`,{missing});}
/** @internal */
export function datumTerm(raw:JsonObject|null,datum:string|null|undefined,context:Context,published=false):number {
    datum=datum??'mean_level';if(datum==='mean_level'&&!published){context.datumName=datum;return 0;}
    const named=obj(raw,'named'),basis=obj(raw,'basis'),mean=!published&&str(raw,'zero')==='harmonic_mean'?0:num(raw,'msl_offset_m');if(mean===null)unavailable('msl_offset_m');
    if(datum==='zero'&&!published){context.datumName=str(raw,'zero_name')??str(raw,'zero')??'unknown';return mean;}
    const key=datum==='chart'?str(raw,'chart_datum'):datum;if(key===null)unavailable('chart_datum');
    const value=num(named,key);if(value===null)unavailable(key);const b=obj(basis,key);
    if(published&&b?.['kind']!=='published')unavailable('published chart datum');
    context.datumName=key;context.datumKind=str(b,'kind');context.datumUncertainty=num(b,'uncertainty_m');return mean-value;
}
function subordinateDatum(offsets:JsonObject,datum:string|null|undefined,context:Context):number {
    const d=obj(offsets,'datum'),named=obj(d,'named'),chart=str(d,'chart_datum'),key=datum===null||datum===undefined||datum==='chart'?chart:datum;
    let term=0;if(datum!==null&&datum!==undefined&&datum!=='chart'){const level=key===null?null:num(named,key);if(level===null)unavailable(datum);term=(chart===null?0:num(named,chart)??0)-level;}
    const b=key===null?null:obj(obj(d,'basis'),key);context.datumName=key;context.datumKind=str(b,'kind');context.datumUncertainty=num(b,'uncertainty_m');return term;
}
function reference(release:Release,offsets:JsonObject,quantity:string,binNumber:number|null=null):readonly[Station,ConstantSet] {
    const id=str(offsets,'reference_station_id'),station=id===null?null:release.station(id);
    const constants=station?.constantSets({includeNoConstants:true}).find(s=>s.quantity===quantity&&(s.qc_status==='ok'||s.qc_status==='flagged')&&(quantity==='water_level'?s.source==='noaa':objects(s.raw,'current_bins').some(b=>b['bin']===binNumber)));
    if(!station||!constants)throw new X.ReferenceUnavailableError(`reference ${id} has no usable set`,{reference_station_id:id});
    if(release._commercialOnly)for(const licenceId of [str(offsets,'licence_id'),constants.licence.licence_id])if(licenceId!==null&&!release.licence(licenceId)?.commercial_use)throw new X.ReferenceUnavailableError(`commercial_only refuses reference licence ${licenceId}`,{reference_station_id:id});return [station,constants];
}
/** @internal */
export function bin(station:Station,bins:readonly JsonObject[],requested:number|null|undefined):JsonObject {
    let selected=requested??num(station.raw,'default_current_bin');if(selected===null&&bins.length)selected=Math.min(...bins.map(b=>num(b,'bin')??Infinity));
    const row=bins.find(b=>b['bin']===selected);if(!row)throw new X.BinNotFoundError(`binNumber ${selected} is not available`);return row;
}
/** @internal */
export function currentContext(context:Context,row:JsonObject):void {
    context.currentBin=row;const azimuth=num(row,'azimuth_deg')??0,flood=num(row,'mean_flood_dir_deg');
    context.sigma=flood===null||Math.cos((azimuth-flood)*RAD)>=0?1:-1;
    context.total=new Sum(context.table,objects(row,'constituents'),{amplitude:'major_amplitude_ms',phase:'major_phase_deg',mean:num(row,'mean_major_ms')??0});
    context.minor=new Sum(context.table,objects(row,'constituents'),{amplitude:'minor_amplitude_ms',phase:'minor_phase_deg',mean:num(row,'mean_minor_ms')??0});
}
function context(release:Release,input:Station|string,quantity:string,setId:string|null|undefined,datum:string|null|undefined=null,binNumber:number|null|undefined=null,series=false,offsetId:string|null|undefined=null):Context {
    const station=stationFor(release,input);options(setId,datum,binNumber);
    validateOffsetArguments(setId,offsetId);
    let constants=chosen(release,station,setId),usable=constants!==null&&(constants.qc_status==='ok'||constants.qc_status==='flagged');
    const tideOffsets=obj(station.raw,'subordinate_offsets'),currentOffsets=objects(station.raw,'current_offsets'),historical=tideOffsets!==null&&str(tideOffsets,'offset_id')!==null;
    if(offsetId!=null){if(!historical||tideOffsets?.['offset_id']!==offsetId)throw new X.InvalidArgumentError(`offsetId ${offsetId} is not a profile of ${station.station_id}`);usable=false;}
    const blockedBetter=historical&&offsetId==null&&release._betterHistoricalPath(station);
    if(setId==null&&!usable&&station.type==='subordinate'&&(tideOffsets&&!blockedBetter||currentOffsets.length)){
        if(tideOffsets){
            if(quantity!=='water_level')throw new X.QuantityMismatchError('tide offsets need water_level');
            const kind=str(tideOffsets,'height_adjusted_type');if(kind!=='R'&&kind!=='A')throw new X.InvalidArgumentError(`height_adjusted_type ${kind} is not R or A`);
            if(historical&&release.historicalOffsetsPolicy==='exclude')throw new X.HistoricalOffsetsExcludedError('historical_offsets_policy=exclude refuses historical prediction');
            const [parent,selected]=reference(release,tideOffsets,quantity);constants=selected;
            if(historical)requireHistoricalOffset(release,tideOffsets,constants,blockedBetter,offsetId!=null);
            const table=tableFor(release,constants);
            if(historical)requireHistoricalTableCompatibility(table,constants.convention);
            const result=contextFor(station,constants,table);result.reference=parent;result.offsets=tideOffsets;
            new Sum(table,objects(constants.raw,'constituents'));
            const referenceTerm=datumTerm(obj(constants.raw,'datum'),'chart',contextFor(parent,constants,table),true),subTerm=subordinateDatum(tideOffsets,datum,result);
            const highTime=num(tideOffsets,'time_offset_high_min')??0,lowTime=num(tideOffsets,'time_offset_low_min')??0,identity=kind==='R'?1:0;
            const highHeight=num(tideOffsets,'height_offset_high')??identity,lowHeight=num(tideOffsets,'height_offset_low')??identity;
            if(kind==='R'&&(highHeight<=0||lowHeight<=0))throw new X.InvalidArgumentError('height_offset ratio must be positive');
            if(highTime===lowTime&&highHeight===lowHeight){result.method='folded_offsets';const multiplier=kind==='R'?highHeight:1,add=kind==='A'?highHeight:0;result.total=new Sum(table,objects(constants.raw,'constituents'),{mean:multiplier*referenceTerm+add+subTerm,multiplier,shiftHours:highTime/60});}
            else {result.method='offsets';result.total=new Sum(table,objects(constants.raw,'constituents'),{mean:referenceTerm});result.offsets={...tideOffsets,_subterm:subTerm};if(series)throw new X.ExtremesOnlyError('high and low water offsets differ, so the station has no exact curve');}
            return result;
        }
        if(quantity!=='current')throw new X.QuantityMismatchError('current offsets need current');
        const entry=bin(station,currentOffsets,binNumber),[parent,selected]=reference(release,entry,quantity,num(entry,'reference_bin')),table=tableFor(release,selected),result=contextFor(station,selected,table);
        result.method='offsets';result.reference=parent;result.referenceBin=num(entry,'reference_bin');result.binNumber=num(entry,'bin');result.offsets=entry;
        currentContext(result,bin(parent,objects(selected.raw,'current_bins'),result.referenceBin));if(series)throw new X.ExtremesOnlyError('subordinate currents provide events only');return result;
    }
    if(!usable||!constants)throw new X.NoConstantsError(`no usable constants: ${constants?.qc_status ?? null}${release._commercialOnly?' (commercial_only)':''}`);
    if(constants.quantity!==quantity)throw new X.QuantityMismatchError(`${quantity} requires that quantity of constants`);
    const table=tableFor(release,constants),result=contextFor(station,constants,table);
    if(quantity==='water_level'){result.total=new Sum(table,objects(constants.raw,'constituents'));result.total.mean=datumTerm(obj(constants.raw,'datum'),datum,result);}
    else {const row=bin(station,objects(constants.raw,'current_bins'),binNumber);result.binNumber=num(row,'bin');currentContext(result,row);}return result;
}
function resultFields(release:Release,c:Context,datum:string|null|undefined=null) {
    return {station_id:c.station.station_id,timezone:c.station.timezone,method:c.method,set_id:c.constants.set_id as string|null,convention_id:c.constants.convention.convention_id,astro_table_id:str(c.table._raw,'astro_table_id')??'',reference_station_id:c.reference?.station_id??null,reference_bin:c.referenceBin,datum:datum??null,datum_name:c.datumName,datum_kind:c.datumKind,datum_uncertainty_m:c.datumUncertainty,tz:null,tz_version:null,release:release.datestamp,algorithm:'otc-predict-1'};
}
function tideFields(release:Release,c:Context,datum:string|null|undefined=null) {
    const fields={...resultFields(release,c,datum),offset_id:null as string|null,offset_source:null as string|null,offset_source_version:null as string|null,historical_offsets:false,current_validity:null as string|null,current_accuracy:null as string|null,reference_set_id:null as string|null,reference_source_version:null as string|null,reference_2020_equivalence:null as string|null,source_note:null as string|null};
    if(c.offsets?.['offset_id']){const vintage=obj(c.offsets,'vintage');Object.assign(fields,{set_id:null,offset_id:str(c.offsets,'offset_id'),offset_source:str(c.offsets,'source'),offset_source_version:str(c.offsets,'source_version'),historical_offsets:true,current_validity:str(vintage,'current_validity'),current_accuracy:str(vintage,'current_accuracy'),reference_set_id:c.constants.set_id,reference_source_version:c.constants.source_version,reference_2020_equivalence:str(vintage,'reference_2020_equivalence'),source_note:'OTC historical-offset calculation using NOAA2020 parameters; retired NOAA profile; current validity unestablished; current accuracy unverified.'});}return fields;
}
export function heights(release:Release,station:Station|string,opts:HeightWindowOptions):HeightSeries {
    const step=opts.stepS===undefined?600:opts.stepS,[start,stop]=window(opts.start,opts.stop,step),c=context(release,station,'water_level',opts.setId,opts.datum,null,true,opts.offsetId),items:HeightPoint[]=[];
    for(let t=start;t<stop;t+=step)items.push(new HeightPoint({time:utc(t),height_m:c.total.value(t),local_time:null,utc_offset_s:null}));return new HeightSeries({...tideFields(release,c,opts.datum),items});
}
export function heightsAt(release:Release,station:Station|string,times:readonly Date[],opts:HeightOptions={}):HeightSeries {
    const seconds=predictionSeconds(times),c=context(release,station,'water_level',opts.setId,opts.datum,null,true,opts.offsetId);
    return heightSeriesFromContext(release,c,seconds,opts.datum);
}
/** @internal Original sequence/instant guard phase; no model selection or evaluation. */
export function predictionSeconds(times:readonly Date[]):number[] {
    if(!Array.isArray(times))throw new X.InvalidArgumentError('times must be a sequence of Dates');return times.map(instant);
}
/** @internal Original offset option guards, after station and prediction options. */
export function validateOffsetArguments(setId:string|null|undefined,offsetId:string|null|undefined):void {
    if(offsetId!==null&&offsetId!==undefined&&typeof offsetId!=='string')throw new X.InvalidArgumentError('offsetId must be a string');
    if(offsetId!=null&&setId!=null)throw new X.InvalidArgumentError('setId and offsetId are mutually exclusive');
}
/** @internal Evaluate only an already selected native context; caller owns selection/window validation. */
export function heightSeriesFromContext(release:Release,c:Context,seconds:readonly number[],datum:string|null|undefined=null):HeightSeries {
    return new HeightSeries({...tideFields(release,c,datum),items:seconds.map(t=>new HeightPoint({time:utc(t),height_m:c.total.value(t),local_time:null,utc_offset_s:null}))});
}
export function extremes(release:Release,station:Station|string,opts:Omit<HeightWindowOptions,'stepS'>):ExtremeList {
    const [start,stop]=window(opts.start,opts.stop),c=context(release,station,'water_level',opts.setId,opts.datum,null,false,opts.offsetId);let candidates;
    if(c.method==='offsets'&&start!==stop){const off=c.offsets as JsonObject,margin=Math.max(120,Math.max(Math.abs(num(off,'time_offset_high_min')??0),Math.abs(num(off,'time_offset_low_min')??0))+60)*60;
        candidates=events(c.total,start-margin,stop+margin).map(([root,kind,value]):[number,string,number]=>{const height=num(off,`height_offset_${kind}`);return [root+(num(off,`time_offset_${kind}_min`)??0)*60,kind,(off['height_adjusted_type']==='R'?value*(height??1):value+(height??0))+(num(off,'_subterm')??0)];}).sort((a,b)=>Math.floor(a[0]+0.5)-Math.floor(b[0]+0.5));
    }else candidates=events(c.total,start,stop);
    const items=candidates.filter(([t])=>start<=Math.floor(t+0.5)&&Math.floor(t+0.5)<stop).map(([t,kind,value])=>new Extreme({time:utc(Math.floor(t+0.5)),type:kind as ExtremeType,height_m:value,local_time:null,utc_offset_s:null}));return new ExtremeList({...tideFields(release,c,opts.datum),items});
}
function currentEventCandidates(c:Context,start:number,stop:number,eventSource:(total:Sum,start:number,stop:number,slack?:boolean)=>Event[]):[number,CurrentEventType,number,number|null][] {
    const row=c.currentBin as JsonObject,total=new Sum(c.table,objects(row,'constituents'),{amplitude:'major_amplitude_ms',phase:'major_phase_deg',multiplier:c.sigma,mean:c.sigma*(num(row,'mean_major_ms')??0)}),candidates:[number,CurrentEventType,number,number|null][]=[];
    for(const [t,kind,value] of eventSource(total,start,stop)){if(kind==='high'&&value>0)candidates.push([t,'max_flood',value,num(row,'mean_flood_dir_deg')]);else if(kind==='low'&&value<0)candidates.push([t,'max_ebb',value,num(row,'mean_ebb_dir_deg')]);}
    for(const [t,kind] of eventSource(total,start,stop,true))candidates.push([t,kind as CurrentEventType,0,null]);return candidates.sort((a,b)=>a[0]-b[0]);
}
function currentEventsFor(c:Context,start:number,stop:number):[number,CurrentEventType,number,number|null][] {return currentEventCandidates(c,start,stop,events);}
/** @internal Same selected-bin peak/slack assembly, before reporting-window filtering. */
export function unroundedCurrentEventsFor(c:Context,start:number,stop:number):[number,CurrentEventType,number,number|null][] {return currentEventCandidates(c,start,stop,unroundedEvents);}
export function currents(release:Release,station:Station|string,opts:CurrentWindowOptions):CurrentSeries {
    const step=opts.stepS===undefined?600:opts.stepS,[start,stop]=window(opts.start,opts.stop,step),c=context(release,station,'current',opts.setId,null,opts.binNumber,true),theta=(num(c.currentBin,'azimuth_deg')??0)*RAD,items:CurrentPoint[]=[];
    for(let t=start;t<stop;t+=step){const major=c.total.value(t),minor=(c.minor as Sum).value(t),east=major*Math.sin(theta)+minor*Math.sin(theta+Math.PI/2),north=major*Math.cos(theta)+minor*Math.cos(theta+Math.PI/2),speed=Math.hypot(east,north),direction=speed<1e-9?null:angle(Math.atan2(east,north)/RAD);items.push(new CurrentPoint({time:utc(t),velocity_major_ms:c.sigma*major,velocity_minor_ms:c.sigma*minor,speed_ms:speed,direction_deg:direction,local_time:null,utc_offset_s:null}));}
    return new CurrentSeries({...resultFields(release,c),items,bin_number:c.binNumber as number});
}
export function currentEvents(release:Release,station:Station|string,opts:Omit<CurrentWindowOptions,'stepS'>):CurrentEventList {
    const [start,stop]=window(opts.start,opts.stop),c=context(release,station,'current',opts.setId,null,opts.binNumber);let candidates;
    if(c.method==='offsets'){const entry=c.offsets as JsonObject,kinds:CurrentEventType[]=['max_flood','max_ebb','slack_before_flood','slack_before_ebb'],kept=kinds.filter(kind=>num(entry,`time_adj_${kind}_min`)!==null&&(kind.startsWith('slack')||num(entry,kind==='max_flood'?'flood_amp_ratio':'ebb_amp_ratio')!==null));c.omitted=kinds.filter(k=>!kept.includes(k));
        const margin=Math.max(120,Math.max(0,...kept.map(k=>Math.abs(num(entry,`time_adj_${k}_min`) as number)))+60)*60;
        candidates=(start===stop?[]:currentEventsFor(c,start-margin,stop+margin)).filter(([,kind])=>kept.includes(kind)).map(([root,kind,value,direction]):[number,CurrentEventType,number,number|null]=>{const time=root+(num(entry,`time_adj_${kind}_min`) as number)*60;if(kind==='max_flood'||kind==='max_ebb'){value*=num(entry,kind==='max_flood'?'flood_amp_ratio':'ebb_amp_ratio') as number;direction=num(entry,kind==='max_flood'?'mean_flood_dir_deg':'mean_ebb_dir_deg');}return [time,kind,value,direction];}).sort((a,b)=>Math.floor(a[0]+0.5)-Math.floor(b[0]+0.5));
    }else candidates=currentEventsFor(c,start,stop);
    const items=candidates.filter(([t])=>start<=Math.floor(t+0.5)&&Math.floor(t+0.5)<stop).map(([t,type,value,direction])=>new CurrentEvent({time:utc(Math.floor(t+0.5)),type,velocity_ms:value,direction_deg:direction,local_time:null,utc_offset_s:null}));return new CurrentEventList({...resultFields(release,c),items,bin_number:c.binNumber as number,omitted_event_types:c.omitted});
}
/** @internal Discovery validates the same model and own policy as prediction, without evaluating a time window. */
export function historicalDiscovery(release:Release,station:Station):boolean {try{context(release,station,'water_level',null,'chart');return true;}catch(e){if(e instanceof X.OpenTideConstantsError)return false;throw e;}}
