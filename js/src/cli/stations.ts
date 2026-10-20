import { parseArgs } from "node:util";
import { InvalidArgumentError, OpenTideConstants, type OpenOptions } from "../index.js";

const usage = `Usage:
    otc stations [--query <name>] [options]
    otc search <name> [options]

Options:
    --file <path>          Open a local release file
    --release <datestamp>  Pin a release (default: latest)
    --cache-dir <path>     Use this SDK cache directory
    --offline             Use cached data without network access
    --base-url <url>       Use a release mirror
    --mode <eager|stream>  Select the SDK loading mode
    --limit <count>        Limit name-search results
    --json                Write {"stations": [...]} instead of a text table
    --help                Show this help
`;

/** The CLI delegates discovery and cache behavior to the public SDK. */
export async function runStations(args: string[]): Promise<string> {
    const command = args[0];
    if (command === undefined || command === "--help") return usage;
    if (command !== "stations" && command !== "search") {
        throw new InvalidArgumentError(`unknown command ${command}; use otc --help`);
    }
    const { values, positionals } = parseArgs({
        args: args.slice(1),
        allowPositionals: true,
        options: {
            file: { type: "string" },
            release: { type: "string" },
            "cache-dir": { type: "string" },
            offline: { type: "boolean" },
            "base-url": { type: "string" },
            mode: { type: "string" },
            query: { type: "string" },
            limit: { type: "string" },
            json: { type: "boolean" },
            help: { type: "boolean" },
        },
    });
    if (values.help) return usage;
    if (command === "search" ? positionals.length !== 1 || values.query !== undefined : positionals.length !== 0) {
        throw new InvalidArgumentError("use otc search <name> or otc stations --query <name>; quote names containing spaces");
    }
    const name = command === "search" ? positionals[0] : values.query;
    if (values.limit !== undefined && name === undefined) {
        throw new InvalidArgumentError("--limit requires a name search");
    }
    if (values.mode !== undefined && values.mode !== "eager" && values.mode !== "stream") {
        throw new InvalidArgumentError("--mode must be eager or stream");
    }
    const options: OpenOptions = {
        file: values.file,
        release: values.release,
        cacheDir: values["cache-dir"],
        offline: values.offline,
        baseUrl: values["base-url"],
        mode: values.mode,
    };
    const client = await OpenTideConstants.open(options);
    try {
        const stations = name === undefined ? client.stations() : client.search({
            name, limit: values.limit === undefined ? undefined : Number(values.limit),
        });
        const rows = stations.map((station) => ({
            station_id: station.station_id,
            name: station.name,
            lat: station.lat,
            lon: station.lon,
            country: station.country,
            type: station.type,
            kind: station.kind,
        }));
        if (values.json) return JSON.stringify({ stations: rows }) + "\n";
        const header = "station_id\tname\tlat\tlon\tcountry\ttype\tkind";
        const lines = rows.map((row) => Object.values(row).map((value) => String(value ?? "").replace(/[\t\r\n]/g, " ")).join("\t"));
        return [header, ...lines].join("\n") + "\n";
    } finally {
        await client.close();
    }
}
