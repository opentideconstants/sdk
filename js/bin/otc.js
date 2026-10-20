#!/usr/bin/env node
import { runStations } from "../dist/cli/stations.js";
import { OpenTideConstantsError } from "../dist/index.js";

try {
    process.stdout.write(await runStations(process.argv.slice(2)));
} catch (error) {
    const code = error instanceof OpenTideConstantsError ? `${error.code}: ` : "";
    process.stderr.write(`otc: ${code}${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
}
