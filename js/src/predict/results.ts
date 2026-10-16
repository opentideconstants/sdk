import {deepFreeze,type JsonObject} from '../json.js';
import type {ExtremeType,CurrentEventType,PredictionMethod} from '../types.js';
import {localize} from './local.js';

/** @internal Native Date value with mutators disabled, retaining Date access/serialization. */
function immutableDate(value: Date): Date {
    const result=new Date(value.getTime());
    for(const key of Object.getOwnPropertyNames(Date.prototype)) if(key.startsWith('set')) Object.defineProperty(result,key,{value:()=>{throw new TypeError('prediction times are immutable');},writable:false,enumerable:false});
    return Object.freeze(result);
}

export class HeightPoint {
    readonly time: Date;
    readonly height_m: number;
    readonly local_time: string | null;
    readonly utc_offset_s: number | null;
    constructor(fields: HeightPoint) {
        this.time = immutableDate(fields.time);
        this.height_m = fields.height_m;
        this.local_time = fields.local_time;
        this.utc_offset_s = fields.utc_offset_s;
        Object.freeze(this);
    }
}

export class Extreme {
    readonly time: Date;
    readonly type: ExtremeType;
    readonly height_m: number;
    readonly local_time: string | null;
    readonly utc_offset_s: number | null;
    constructor(fields: Extreme) {
        this.time = immutableDate(fields.time);
        this.type = fields.type;
        this.height_m = fields.height_m;
        this.local_time = fields.local_time;
        this.utc_offset_s = fields.utc_offset_s;
        Object.freeze(this);
    }
}

export class CurrentPoint {
    readonly time: Date;
    readonly velocity_major_ms: number;
    readonly velocity_minor_ms: number;
    readonly speed_ms: number;
    readonly direction_deg: number | null;
    readonly local_time: string | null;
    readonly utc_offset_s: number | null;
    constructor(fields: CurrentPoint) {
        this.time = immutableDate(fields.time);
        this.velocity_major_ms = fields.velocity_major_ms;
        this.velocity_minor_ms = fields.velocity_minor_ms;
        this.speed_ms = fields.speed_ms;
        this.direction_deg = fields.direction_deg;
        this.local_time = fields.local_time;
        this.utc_offset_s = fields.utc_offset_s;
        Object.freeze(this);
    }
}

export class CurrentEvent {
    readonly time: Date;
    readonly type: CurrentEventType;
    readonly velocity_ms: number;
    readonly direction_deg: number | null;
    readonly local_time: string | null;
    readonly utc_offset_s: number | null;
    constructor(fields: CurrentEvent) {
        this.time = immutableDate(fields.time);
        this.type = fields.type;
        this.velocity_ms = fields.velocity_ms;
        this.direction_deg = fields.direction_deg;
        this.local_time = fields.local_time;
        this.utc_offset_s = fields.utc_offset_s;
        Object.freeze(this);
    }
}

export class HeightSeries {
    readonly items: readonly HeightPoint[];
    readonly station_id: string;
    readonly timezone: string | null;
    readonly method: PredictionMethod | null;
    readonly set_id: string | null;
    readonly convention_id: string;
    readonly astro_table_id: string;
    readonly reference_station_id: string | null;
    readonly reference_bin: number | null;
    readonly datum: string | null;
    readonly datum_name: string | null;
    readonly datum_kind: string | null;
    readonly datum_uncertainty_m: number | null;
    readonly tz: string | null;
    readonly tz_version: string | null;
    readonly release: string;
    readonly algorithm: string;
    readonly offset_id: string | null;
    readonly offset_source: string | null;
    readonly offset_source_version: string | null;
    readonly historical_offsets: boolean;
    readonly current_validity: string | null;
    readonly current_accuracy: string | null;
    readonly reference_set_id: string | null;
    readonly reference_source_version: string | null;
    readonly reference_2020_equivalence: string | null;
    readonly source_note: string | null;
    constructor(fields: Omit<HeightSeries, 'toLocal'>) {
        this.items = deepFreeze(fields.items);
        this.station_id = fields.station_id;
        this.timezone = fields.timezone;
        this.method = fields.method;
        this.set_id = fields.set_id;
        this.convention_id = fields.convention_id;
        this.astro_table_id = fields.astro_table_id;
        this.reference_station_id = fields.reference_station_id;
        this.reference_bin = fields.reference_bin;
        this.datum = fields.datum;
        this.datum_name = fields.datum_name;
        this.datum_kind = fields.datum_kind;
        this.datum_uncertainty_m = fields.datum_uncertainty_m;
        this.tz = fields.tz;
        this.tz_version = fields.tz_version;
        this.release = fields.release;
        this.algorithm = fields.algorithm;
        this.offset_id = fields.offset_id;
        this.offset_source = fields.offset_source;
        this.offset_source_version = fields.offset_source_version;
        this.historical_offsets = fields.historical_offsets;
        this.current_validity = fields.current_validity;
        this.current_accuracy = fields.current_accuracy;
        this.reference_set_id = fields.reference_set_id;
        this.reference_source_version = fields.reference_source_version;
        this.reference_2020_equivalence = fields.reference_2020_equivalence;
        this.source_note = fields.source_note;
        Object.freeze(this);
    }
    toLocal(tz: string = 'station'): HeightSeries { return localize(this,tz); }
}

export class ExtremeList {
    readonly items: readonly Extreme[];
    readonly station_id: string;
    readonly timezone: string | null;
    readonly method: PredictionMethod | null;
    readonly set_id: string | null;
    readonly convention_id: string;
    readonly astro_table_id: string;
    readonly reference_station_id: string | null;
    readonly reference_bin: number | null;
    readonly datum: string | null;
    readonly datum_name: string | null;
    readonly datum_kind: string | null;
    readonly datum_uncertainty_m: number | null;
    readonly tz: string | null;
    readonly tz_version: string | null;
    readonly release: string;
    readonly algorithm: string;
    readonly offset_id: string | null;
    readonly offset_source: string | null;
    readonly offset_source_version: string | null;
    readonly historical_offsets: boolean;
    readonly current_validity: string | null;
    readonly current_accuracy: string | null;
    readonly reference_set_id: string | null;
    readonly reference_source_version: string | null;
    readonly reference_2020_equivalence: string | null;
    readonly source_note: string | null;
    constructor(fields: Omit<ExtremeList, 'toLocal'>) {
        this.items = deepFreeze(fields.items);
        this.station_id = fields.station_id;
        this.timezone = fields.timezone;
        this.method = fields.method;
        this.set_id = fields.set_id;
        this.convention_id = fields.convention_id;
        this.astro_table_id = fields.astro_table_id;
        this.reference_station_id = fields.reference_station_id;
        this.reference_bin = fields.reference_bin;
        this.datum = fields.datum;
        this.datum_name = fields.datum_name;
        this.datum_kind = fields.datum_kind;
        this.datum_uncertainty_m = fields.datum_uncertainty_m;
        this.tz = fields.tz;
        this.tz_version = fields.tz_version;
        this.release = fields.release;
        this.algorithm = fields.algorithm;
        this.offset_id = fields.offset_id;
        this.offset_source = fields.offset_source;
        this.offset_source_version = fields.offset_source_version;
        this.historical_offsets = fields.historical_offsets;
        this.current_validity = fields.current_validity;
        this.current_accuracy = fields.current_accuracy;
        this.reference_set_id = fields.reference_set_id;
        this.reference_source_version = fields.reference_source_version;
        this.reference_2020_equivalence = fields.reference_2020_equivalence;
        this.source_note = fields.source_note;
        Object.freeze(this);
    }
    toLocal(tz: string = 'station'): ExtremeList { return localize(this,tz); }
}

export class CurrentSeries {
    readonly items: readonly CurrentPoint[];
    readonly station_id: string;
    readonly timezone: string | null;
    readonly method: PredictionMethod | null;
    readonly set_id: string | null;
    readonly convention_id: string;
    readonly astro_table_id: string;
    readonly reference_station_id: string | null;
    readonly reference_bin: number | null;
    readonly datum: string | null;
    readonly datum_name: string | null;
    readonly datum_kind: string | null;
    readonly datum_uncertainty_m: number | null;
    readonly bin_number: number;
    readonly tz: string | null;
    readonly tz_version: string | null;
    readonly release: string;
    readonly algorithm: string;
    constructor(fields: Omit<CurrentSeries, 'toLocal'>) {
        this.items = deepFreeze(fields.items);
        this.station_id = fields.station_id;
        this.timezone = fields.timezone;
        this.method = fields.method;
        this.set_id = fields.set_id;
        this.convention_id = fields.convention_id;
        this.astro_table_id = fields.astro_table_id;
        this.reference_station_id = fields.reference_station_id;
        this.reference_bin = fields.reference_bin;
        this.datum = fields.datum;
        this.datum_name = fields.datum_name;
        this.datum_kind = fields.datum_kind;
        this.datum_uncertainty_m = fields.datum_uncertainty_m;
        this.bin_number = fields.bin_number;
        this.tz = fields.tz;
        this.tz_version = fields.tz_version;
        this.release = fields.release;
        this.algorithm = fields.algorithm;
        Object.freeze(this);
    }
    toLocal(tz: string = 'station'): CurrentSeries { return localize(this,tz); }
}

export class CurrentEventList {
    readonly items: readonly CurrentEvent[];
    readonly station_id: string;
    readonly timezone: string | null;
    readonly method: PredictionMethod | null;
    readonly set_id: string | null;
    readonly convention_id: string;
    readonly astro_table_id: string;
    readonly reference_station_id: string | null;
    readonly reference_bin: number | null;
    readonly datum: string | null;
    readonly datum_name: string | null;
    readonly datum_kind: string | null;
    readonly datum_uncertainty_m: number | null;
    readonly bin_number: number;
    readonly omitted_event_types: readonly CurrentEventType[] | null;
    readonly tz: string | null;
    readonly tz_version: string | null;
    readonly release: string;
    readonly algorithm: string;
    constructor(fields: Omit<CurrentEventList, 'toLocal'>) {
        this.items = deepFreeze(fields.items);
        this.station_id = fields.station_id;
        this.timezone = fields.timezone;
        this.method = fields.method;
        this.set_id = fields.set_id;
        this.convention_id = fields.convention_id;
        this.astro_table_id = fields.astro_table_id;
        this.reference_station_id = fields.reference_station_id;
        this.reference_bin = fields.reference_bin;
        this.datum = fields.datum;
        this.datum_name = fields.datum_name;
        this.datum_kind = fields.datum_kind;
        this.datum_uncertainty_m = fields.datum_uncertainty_m;
        this.bin_number = fields.bin_number;
        this.omitted_event_types = deepFreeze(fields.omitted_event_types);
        this.tz = fields.tz;
        this.tz_version = fields.tz_version;
        this.release = fields.release;
        this.algorithm = fields.algorithm;
        Object.freeze(this);
    }
    toLocal(tz: string = 'station'): CurrentEventList { return localize(this,tz); }
}

export class DatumLevel {
    readonly key: string;
    readonly value_m: number;
    readonly above_chart_m: number | null;
    readonly kind: string | null;
    readonly method: string | null;
    readonly source_name: string | null;
    readonly epoch: JsonObject | null;
    readonly data_span: JsonObject | null;
    readonly control_station_id: string | null;
    readonly control_set_id: string | null;
    readonly control_source_id: string | null;
    readonly uncertainty_m: number | null;
    readonly uncertainty_basis: string | null;
    readonly flags: readonly string[];
    readonly fallback?: JsonObject | null;
    constructor(fields: DatumLevel) {
        this.key = fields.key;
        this.value_m = fields.value_m;
        this.above_chart_m = fields.above_chart_m;
        this.kind = fields.kind;
        this.method = fields.method;
        this.source_name = fields.source_name;
        this.epoch = deepFreeze(fields.epoch);
        this.data_span = deepFreeze(fields.data_span);
        this.control_station_id = fields.control_station_id;
        this.control_set_id = fields.control_set_id;
        this.control_source_id = fields.control_source_id;
        this.uncertainty_m = fields.uncertainty_m;
        this.uncertainty_basis = fields.uncertainty_basis;
        this.flags = deepFreeze(fields.flags);
        this.fallback = deepFreeze(fields.fallback ?? null);
        Object.freeze(this);
    }
}

export class DatumInfo {
    readonly set_id: string | null;
    readonly zero: string | null;
    readonly zero_name: string | null;
    readonly chart_datum: string | null;
    readonly msl_offset_m: number | null;
    readonly levels: readonly DatumLevel[];
    constructor(fields: DatumInfo) {
        this.set_id = fields.set_id;
        this.zero = fields.zero;
        this.zero_name = fields.zero_name;
        this.chart_datum = fields.chart_datum;
        this.msl_offset_m = fields.msl_offset_m;
        this.levels = deepFreeze(fields.levels);
        Object.freeze(this);
    }
}

export class Ranges {
    readonly mn: number | null;
    readonly gt: number | null;
    readonly dhq: number | null;
    readonly dlq: number | null;
    constructor(fields: Ranges) {
        this.mn = fields.mn;
        this.gt = fields.gt;
        this.dhq = fields.dhq;
        this.dlq = fields.dlq;
        Object.freeze(this);
    }
}
