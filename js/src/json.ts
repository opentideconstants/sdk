/** @internal JSON helpers for tolerant reading (spec 7.3). */
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

/** @internal An ISO 8601 time as a Date, or null. */
export function time(v: Json | undefined): Date | null {
    if (typeof v !== "string") return null;
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d;
}
