import { InvalidArgumentError, UnsupportedConstituentError, TimeOutOfRangeError } from '../errors.js';
import { deepFreeze, isObject, num, str, type JsonObject } from '../json.js';

/** @internal */
export function instant(value: Date): number {
    if (!(value instanceof Date) || !Number.isFinite(value.getTime())) throw new InvalidArgumentError('an instant must be a valid Date');
    return Math.floor(value.getTime() / 1000);
}
/** @internal */
export function utc(seconds: number): Date { return new Date(seconds * 1000); }
/** @internal */
export function yearStart(year: number): number {
    const date = new Date(0); date.setUTCFullYear(year, 0, 1); date.setUTCHours(0, 0, 0, 0); return date.getTime() / 1000;
}
/** @internal */
export function angle(value: number): number { const reduced = value - 360 * Math.floor(value / 360); return reduced === 360 ? 0 : reduced; }
/** @internal */
export interface AstroRow { readonly speed_deg_per_hour: number; readonly v0u_deg: readonly number[]; readonly f: readonly number[]; }

export class AstroTable {
    readonly #raw: JsonObject;
    readonly #first: number;
    readonly #last: number;
    constructor(raw: JsonObject) {
        const bad = (detail: string): never => { throw new InvalidArgumentError(`astro table "${str(raw,'astro_table_id') ?? ''}" ${detail}`); };
        const first = num(raw,'first_year'), last = num(raw,'last_year');
        if (first === null || last === null || !Number.isInteger(first) || !Number.isInteger(last) || first > last) bad('first_year and last_year must be ordered integers');
        const rows = raw['constituents'];
        if (!isObject(rows)) bad('constituents must be an object');
        if (isObject(rows)) for (const [name,row] of Object.entries(rows)) {
            if (!isObject(row)) bad(`row "${name}": must be an object`);
            if (isObject(row)) {
                for (const key of ['v0u_deg','f']) {
                    const values = row[key];
                    if (!Array.isArray(values) || values.length !== (last as number) - (first as number) + 1 || !values.every(v => typeof v === 'number' && Number.isFinite(v))) bad(`row "${name}": ${key} must contain ${(last as number)-(first as number)+1} numbers`);
                }
                const speed = row['speed_deg_per_hour'];
                if (speed !== undefined && speed !== null && (typeof speed !== 'number' || !Number.isFinite(speed) || speed < 0)) bad(`row "${name}": speed_deg_per_hour must be a nonnegative number`);
            }
        }
        this.#first = first as number; this.#last = last as number; this.#raw = deepFreeze(raw); Object.freeze(this);
    }
    get validRange(): readonly [number,number] { return Object.freeze([this.#first,this.#last]); }
    /** @internal */
    get _raw(): JsonObject { return this.#raw; }
    /** @internal */
    _index(year: number): number {
        if (typeof year !== 'number' || !Number.isInteger(year)) throw new InvalidArgumentError('year must be an integer');
        if (year < this.#first || year > this.#last) throw new TimeOutOfRangeError(`year ${year} is outside the astro table`,{first_year:this.#first,last_year:this.#last});
        return year-this.#first;
    }
    /** @internal */
    _row(name: string): AstroRow {
        const rows=this.#raw['constituents']; const row=isObject(rows)&&typeof name==='string'?rows[name]:null;
        if (!isObject(row) || num(row,'speed_deg_per_hour')===null) throw new UnsupportedConstituentError(`unsupported constituent ${name}`,{constituent:name});
        return row as unknown as AstroRow;
    }
    equilibriumArgument(name: string, at: Date): number { const seconds=instant(at), row=this._row(name), year=utc(seconds).getUTCFullYear(); return angle(row.v0u_deg[this._index(year)]+row.speed_deg_per_hour*((seconds-yearStart(year))/3600)); }
    nodeFactor(name: string, at: Date): number { const seconds=instant(at), row=this._row(name); return row.f[this._index(utc(seconds).getUTCFullYear())]; }
    equilibriumForYear(name: string, year: number): number { return this._row(name).v0u_deg[this._index(year)]; }
    nodeFactorForYear(name: string, year: number): number { return this._row(name).f[this._index(year)]; }
}
