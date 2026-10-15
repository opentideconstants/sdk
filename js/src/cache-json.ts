/** @internal Encode only SDK-generated cache JSON (B28), never original release or pointer bytes. */
import { isObject } from "./json.js";

const encoder = new TextEncoder();

function string(value: string): string {
    let output = '"';
    for (const character of value) {
        const scalar = character.codePointAt(0)!;
        if (scalar >= 0xd800 && scalar <= 0xdfff) throw new TypeError("cache JSON contains an unpaired surrogate");
        if (scalar < 0x20) output += `\\u${scalar.toString(16).padStart(4, "0")}`;
        else if (character === '"' || character === "\\") output += "\\" + character;
        else output += character;
    }
    return output + '"';
}

function compareKeys(left: string, right: string): number {
    const a = Array.from(left, character => character.codePointAt(0)!);
    const b = Array.from(right, character => character.codePointAt(0)!);
    for (let index = 0; index < Math.min(a.length, b.length); index++) {
        const difference = a[index]! - b[index]!;
        if (difference !== 0) return difference;
    }
    return a.length - b.length;
}

function json(value: unknown): string {
    if (value === null) return "null";
    if (typeof value === "string") return string(value);
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") {
        if (!Number.isFinite(value)) throw new TypeError("cache JSON contains a nonfinite number");
        // ECMAScript's binary64 conversion uses the closest shortest roundtrip,
        // even ties and B28's plain-notation bounds. Only the exponent '+' differs.
        return value.toString().replace("e+", "e");
    }
    if (Array.isArray(value)) return "[" + value.map(json).join(",") + "]";
    if (isObject(value)) {
        return "{" + Object.keys(value).sort(compareKeys).map(key => string(key) + ":" + json(value[key])).join(",") + "}";
    }
    throw new TypeError("cache JSON contains a value that is not JSON");
}

/** @internal B28 encode_cache_json(cache_document) -> cache_bytes. */
export function encodeCacheJson(cacheDocument: unknown): Uint8Array {
    return encoder.encode(json(cacheDocument));
}
