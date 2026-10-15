import type {Release,ConstantSet} from './release.js';
import {str,num,obj,type JsonObject} from './json.js';
import {NoConstantsError,InvalidReleaseError} from './errors.js';
/** @internal Own admission is independent of caller quality flags. */
export function requireHistoricalOffset(release: Release, offsets: JsonObject, reference: ConstantSet, betterPath: boolean, explicit: boolean): void {
    const own=release.licence(str(offsets,'licence_id') ?? '');
    if(!own)throw new InvalidReleaseError('historical own licence does not resolve');
    const bound=obj(obj(offsets,'provenance'),'reference_binding');
    const datum=obj(reference.raw,'datum');
    const eligible=release.historicalOffsetsPolicy!=='exclude' && (explicit||!betterPath)
        && reference.set_id.startsWith(`${str(offsets,'reference_station_id')}/`) && reference.source==='noaa'
        && reference.source_record_id===bound?.['noaa_id'] && reference.quantity==='water_level'
        && reference.qc_status==='ok' && reference.fallback===null
        && (!release._commercialOnly || own.commercial_use && reference.licence.commercial_use)
        && reference.convention.v0_model==='schureman_tcd' && reference.convention.nodal_handling==='f_u_at_prediction'
        && datum?.['chart_datum']==='mllw' && num(datum,'msl_offset_m')!==null
        && obj(datum,'named')?.['mllw']===0 && obj(obj(datum,'basis'),'mllw')?.['kind']==='published';
    if(!eligible)throw new NoConstantsError('historical offsets are ineligible');
}
