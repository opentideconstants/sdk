// A fake SDK module for the runner self-tests (see ../README.md). FAKE_SDK_MODE comes through globalThis.process.
const MODE = (globalThis.process && globalThis.process.env.FAKE_SDK_MODE) || "";
export const VERSION = MODE === "no-version" ? undefined : "9.9.9-fake";
class SdkError extends Error {
    constructor(msg, code, tombstone) { super(msg); this.code = code; this.tombstone = tombstone; }
}
class Tomb { constructor() { this.station_id = "OTC-T-0005"; this.name = "Old Pier"; this.status = "removed"; this.removed_in = "20991231"; this.removed_reason = "duplicate"; this.merged_into = "OTC-T-0001"; } }
class Release {
    get datestamp() { return "20991231.2"; }
    get format_version() { return "1.0"; }
    get tombstoneCount() { if (MODE === "raise") throw new TypeError("not an SDK error"); return 1; }
    get stationCount() { return { inf: Infinity, nan: NaN, bigint: 10n }[MODE] ?? 20; }
    station(id) {
        if (MODE === "station-no-fields") return { station_id: id };
        if (MODE.startsWith("station-without-")) {   // a full station with one field left out (undefined)
            const st = { station_id: id, name: "X", country: "GBR", lat: 1, lon: 2, type: "reference", kind: "tide",
                timezone: "Europe/London", aliases: {}, status: "active", isReference: true, isSubordinate: false,
                isTide: true, isCurrent: false, recommendedSet: null, validation: [{ set_id: "s", reference_source: "noaa",
                    reference_station: null, reference_distance_km: null, window: "2099-01", time_mae_min: 1, time_p95_min: null,
                    time_bias_min: null, height_mae_m: null, range_error_m: null, missed_events: null, extra_events: null,
                    previous_release: null }] };
            const field = MODE.slice("station-without-".length);
            if (field === "previous_release") delete st.validation[0].previous_release;
            else delete st[field];
            return st;
        }
        return null;
    }
    requireStation() { throw new SdkError("removed", "station_removed", new Tomb()); }
    subordinatesOf() { return []; }
}
class Client {
    constructor() { this.release = new Release(); this.loadedFrom = "file"; this.lastError = null; }
    station(id) { return this.release.station(id); }
    requireStation(id) { return this.release.requireStation(id); }
    subordinatesOf(s) { return this.release.subordinatesOf(s); }
    async close() { if (MODE === "close-raises") throw new Error("close failed"); }
}
export const OpenTideConstants = { open: async () => new Client() };
export const OpenTideConstantsError = MODE === "no-error-class" ? undefined : SdkError;
