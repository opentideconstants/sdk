// JSON helpers for tolerant reading (spec 7.3).
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
/** A parsed JSON object, as the file gives it. */
export type JsonObject = { readonly [key: string]: Json };

/** @internal */
export function isObject(v: unknown): v is { [key: string]: Json } {
    return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** @internal */
export function str(o: JsonObject | null | undefined, k: string): string | null {
    const v = o ? o[k] : undefined;
    return typeof v === "string" ? v : null;
}

/** @internal */
export function num(o: JsonObject | null | undefined, k: string): number | null {
    const v = o ? o[k] : undefined;
    return typeof v === "number" ? v : null;
}

/** @internal */
export function obj(o: JsonObject | null | undefined, k: string): JsonObject | null {
    const v = o ? o[k] : undefined;
    return isObject(v) ? v : null;
}

/** @internal */
export function arr(o: JsonObject | null | undefined, k: string): readonly Json[] {
    const v = o ? o[k] : undefined;
    return Array.isArray(v) ? v : [];
}

/** @internal The value as given, or null when absent. */
export function val(o: JsonObject | null | undefined, k: string): Json {
    const v = o ? o[k] : undefined;
    return v === undefined ? null : v;
}

/** @internal Freeze a parsed JSON value in place, deeply. */
export function deepFreeze<T>(v: T): T {
    if (typeof v === "object" && v !== null && !Object.isFrozen(v)) {
        Object.freeze(v);
        for (const k of Object.keys(v)) deepFreeze((v as Record<string, unknown>)[k]);
    }
    return v;
}

/** @internal An enum value, or "other" for a value this SDK does not know (spec 7.3). */
export function en<T extends string>(v: Json | undefined, allowed: readonly T[]): T | "other" | null {
    if (v === null || v === undefined) return null;
    return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : "other";
}

/** An RFC 3339 date-time: a full date, a time with seconds, an optional fraction, and Z or an offset. */
const RFC3339 = /^(([0-9]{4})-([0-9]{2})-([0-9]{2}))[Tt ](([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?)([Zz]|[+-]([0-9]{2}):([0-9]{2}))$/;

/** @internal The days in a month of the proleptic Gregorian calendar (month 1 to 12). */
export function daysInMonth(y: number, m: number): number {
    if (m === 2) return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 29 : 28;
    return [4, 6, 9, 11].includes(m) ? 30 : 31;
}

/**
 * @internal An RFC 3339 time as a Date, or null. A string without a zone offset is not read as local time, so the
 * result never depends on the host's time zone (PK07 T20). Impossible calendar fields, hour 24, a leap second :60
 * and a time out of years 1 to 9999 in UTC are malformed (null): Date would roll them over (CR2 DR6).
 */
export function time(v: Json | undefined): Date | null {
    if (typeof v !== "string") return null;
    const m = RFC3339.exec(v);
    if (!m) return null;
    const [y, mo, d, h, mi, s] = [m[2], m[3], m[4], m[6], m[7], m[8]].map(Number) as [number, number, number, number, number, number];
    if (mo < 1 || mo > 12 || d < 1 || d > daysInMonth(y, mo) || h > 23 || mi > 59 || s > 59) return null;
    if (m[10] !== undefined && (Number(m[10]) > 23 || Number(m[11]) > 59)) return null;
    const t = new Date(`${m[1]}T${m[5]}${(m[9] ?? "").toUpperCase()}`);
    const year = t.getUTCFullYear();
    return Number.isNaN(t.getTime()) || year < 1 || year > 9999 ? null : t;
}
