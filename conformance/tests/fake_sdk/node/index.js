// A fake SDK module for the runner self-tests (see ../README.md). FAKE_SDK_MODE comes through globalThis.process.
const MODE = (globalThis.process && globalThis.process.env.FAKE_SDK_MODE) || "";
export const VERSION = "9.9.9-fake";
export class OpenTideConstantsError extends Error {
    constructor(msg, code, tombstone) { super(msg); this.code = code; this.tombstone = tombstone; }
}
class Tomb { constructor() { this.station_id = "OTC-T-0005"; this.name = "Old Pier"; this.status = "removed"; this.removed_in = "20991231"; this.removed_reason = "duplicate"; this.merged_into = "OTC-T-0001"; } }
class Release {
    get datestamp() { return "20991231.2"; }
    get format_version() { return "1.0"; }
    get stationCount() { return { inf: Infinity, nan: NaN, bigint: 10n }[MODE] ?? 20; }
    station(id) { return MODE === "station-no-fields" ? { station_id: id } : null; }
    requireStation() { throw new OpenTideConstantsError("removed", "station_removed", new Tomb()); }
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
