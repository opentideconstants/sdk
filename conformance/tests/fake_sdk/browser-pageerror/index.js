// A fake browser SDK for the runner self-tests (see ../README.md): stationCount answers 20, and an error escapes
// in the page right after (an uncaught exception outside the op's promise, which the page reports as pageerror).
export const VERSION = "9.9.9-fake";
export class OpenTideConstantsError extends Error {}
class Release {
    get datestamp() { return "20991231.2"; }
    get format_version() { return "1.0"; }
    get stationCount() { setTimeout(() => { throw new Error("fake: an error escaped in the page"); }, 0); return 20; }
}
class Client {
    constructor() { this.release = new Release(); this.loadedFrom = "download"; this.lastError = null; }
    async close() {}
}
export const OpenTideConstants = { open: async () => new Client() };
