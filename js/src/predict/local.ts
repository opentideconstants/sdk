import { UnknownTimeZoneError, LocalTimeUnavailableError } from '../errors.js';
import {HeightSeries,ExtremeList,CurrentSeries,CurrentEventList,HeightPoint,Extreme,CurrentPoint,CurrentEvent} from './results.js';

type Result = HeightSeries | ExtremeList | CurrentSeries | CurrentEventList;
const pad=(n:number,width=2)=>String(n).padStart(width,'0');
/** @internal Original non-string branch only; timezone grammar/Intl remain in localize. */
export function validateLocalTimeType(zone:unknown):asserts zone is string {
    if(typeof zone!=='string')throw new UnknownTimeZoneError(`unknown time zone ${String(zone)}`,{zone:typeof zone==='string'?zone:null});
}
export function localize<T extends Result>(result: T,tz: string): T {
    const zone=tz==='station'?result.timezone:tz;
    validateLocalTimeType(zone);
    if(zone.length>255||!/^[A-Za-z0-9_+-]+(?:\/[A-Za-z0-9_+-]+)*$/.test(zone)||zone.startsWith('posix/')||zone.startsWith('right/')||['posixrules','localtime','Factory'].includes(zone)) throw new UnknownTimeZoneError(`unknown time zone ${String(zone)}`,{zone:typeof zone==='string'?zone:null});
    if(typeof Intl==='undefined'||typeof Intl.DateTimeFormat!=='function') throw new LocalTimeUnavailableError('this runtime needs Intl time-zone support');
    let formatter:Intl.DateTimeFormat;
    try {formatter=new Intl.DateTimeFormat('en-US-u-ca-gregory-nu-latn',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});}
    catch {throw new UnknownTimeZoneError(`unknown time zone ${zone}`,{zone});}
    const node=(globalThis as {process?:{versions?:{tz?:string}}}).process;
    const version=node?.versions?.tz??null;
    const items=result.items.map(item=>{
        const parts=Object.fromEntries(formatter.formatToParts(item.time).map(p=>[p.type,p.value]));
        const wall=new Date(0);wall.setUTCFullYear(Number(parts.year),Number(parts.month)-1,Number(parts.day));wall.setUTCHours(Number(parts.hour),Number(parts.minute),Number(parts.second),0);
        const offset=(wall.getTime()-item.time.getTime())/1000,magnitude=Math.abs(offset);
        const suffix=`${offset>=0?'+':'-'}${pad(Math.floor(magnitude/3600))}:${pad(Math.floor(magnitude%3600/60))}${magnitude%60?':'+pad(magnitude%60):''}`;
        const local_time=`${pad(Number(parts.year),4)}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}${suffix}`;
        const fields={...item,local_time,utc_offset_s:offset};
        if(item instanceof HeightPoint)return new HeightPoint(fields as HeightPoint);
        if(item instanceof Extreme)return new Extreme(fields as Extreme);
        if(item instanceof CurrentPoint)return new CurrentPoint(fields as CurrentPoint);
        return new CurrentEvent(fields as CurrentEvent);
    });
    const fields={...result,items,tz:zone,tz_version:version};
    if(result instanceof HeightSeries)return new HeightSeries(fields as Omit<HeightSeries,'toLocal'>) as T;
    if(result instanceof ExtremeList)return new ExtremeList(fields as Omit<ExtremeList,'toLocal'>) as T;
    if(result instanceof CurrentSeries)return new CurrentSeries(fields as Omit<CurrentSeries,'toLocal'>) as T;
    return new CurrentEventList(fields as Omit<CurrentEventList,'toLocal'>) as T;
}
