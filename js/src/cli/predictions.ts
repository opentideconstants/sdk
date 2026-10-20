import { InvalidArgumentError, type OpenTideConstants, type HeightOptions, type CurrentOptions } from "../index.js";

export type PredictionCommand = "extremes" | "timeline" | "currents";

export function isPredictionCommand(command: string): command is PredictionCommand {
    return command === "extremes" || command === "timeline" || command === "currents";
}

interface PredictionFlags {
    from?: string;
    to?: string;
    step?: string;
    bin?: string;
    datum?: string;
    units?: string;
    json?: boolean;
}

/** Translate CLI arguments; the SDK owns prediction, datum and unit validation. */
export async function runPrediction(client: OpenTideConstants, command: PredictionCommand, station: string, flags: PredictionFlags): Promise<string> {
    if (flags.from === undefined || flags.to === undefined) throw new InvalidArgumentError("predictions require --from and --to");
    if (command === "timeline" && flags.step === undefined) throw new InvalidArgumentError("timeline requires --step in seconds");
    if (command === "extremes" && flags.step !== undefined) throw new InvalidArgumentError("--step applies to timeline and currents");
    if (command !== "currents" && flags.bin !== undefined) throw new InvalidArgumentError("--bin applies to currents");
    if (command === "currents" && flags.datum !== undefined) throw new InvalidArgumentError("--datum applies to height predictions");
    const window = { start: new Date(flags.from), stop: new Date(flags.to) };
    const stepS = flags.step === undefined ? undefined : Number(flags.step);
    // Parsed strings cross the typed API boundary here; native SDK validation remains authoritative.
    const heightOptions = { ...window, datum: flags.datum, units: flags.units as HeightOptions["units"] };
    const result = command === "currents"
        ? await client.currents(station, {
            ...window, stepS, binNumber: flags.bin === undefined ? undefined : Number(flags.bin),
            units: flags.units as CurrentOptions["units"],
        })
        : command === "timeline" ? await client.heights(station, { ...heightOptions, stepS })
            : await client.extremes(station, heightOptions);
    // Public metadata and selected-unit getters, matching the existing native runner encoding.
    const metadataKeys = [
        "station_id", "timezone", "method", "set_id", "convention_id", "astro_table_id", "reference_station_id",
        "reference_bin", "datum", "datum_name", "datum_kind", "datum_uncertainty_m", "tz", "tz_version", "release", "algorithm", "units",
    ] as const;
    const metadata = {
        ...Object.fromEntries(metadataKeys.map((key) => [key, result[key]])),
        bin_number: "bin_number" in result ? result.bin_number : null,
        omitted_event_types: null,
    };
    const items = result.items.map((item) => ({
        ...item,
        time: item.time.toISOString().replace(/\.000Z$/, "Z"),
        ...("height" in item ? { height: item.height } : {
            velocity_major: item.velocity_major, velocity_minor: item.velocity_minor, speed: item.speed,
        }),
    }));
    if (flags.json) return JSON.stringify({ prediction: { ...metadata, items } }) + "\n";
    const lines = Object.entries(metadata).map(([key, value]) => `# ${key}\t${JSON.stringify(value)}`);
    lines.push("", Object.keys(items[0] ?? {}).join("\t"));
    for (const item of items) {
        lines.push(Object.entries(item).map(([key, value]) => JSON.stringify(
            key === "time" ? new Date(item.time).toLocaleString("en-US", { timeZoneName: "short" }) : value,
        )).join("\t"));
    }
    return lines.join("\n") + "\n";
}
