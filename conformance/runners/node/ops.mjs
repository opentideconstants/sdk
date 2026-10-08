// The TypeScript runner's op table (conformance/README.md "Operations" and "Result encodings").
//
// Plain JavaScript with no imports, so the same file runs in Node (runner.mjs) and in a
// browser page (browser-runner.mjs). It calls only the public API of the SDK module it is given.

const FILTERS = ["country", "type", "kind", "source", "source_type"];

function camel(name) {
    return name.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
}

// Build an options object from the case args: absent args are not passed; null is passed as null.
function opts(args, names) {
    const out = {};
    for (const n of names) {
        if (Object.prototype.hasOwnProperty.call(args, n)) out[camel(n)] = args[n];
    }
    return out;
}

function basename(p) {
    const parts = String(p).split(/[\\/]/);
    return parts[parts.length - 1];
}

const pick = (obj, fields) => {
    const out = {};
    for (const f of fields) out[f] = obj == null || obj[f] === undefined ? null : obj[f];
    return out;
};

const CONSTITUENT = ["name", "source_name", "doodson", "speed_deg_per_hour", "amplitude_m", "phase_deg",
    "amp_uncertainty_m", "phase_uncertainty_deg", "kept_reason"];
const CONVENTION = ["convention_id", "phase_reference", "utc_offset_hours", "v0_model", "nodal_handling",
    "nodal_formula_ids", "constituent_table_version", "tables_sha256", "canary"];
const LICENCE = ["licence_id", "spdx", "provider", "citation", "attribution", "url"];
const PROVENANCE = ["build_commit", "adapter_version", "input_sha256", "time_base", "selection_reason", "decision"];
const VALIDATION = ["set_id", "reference_source", "reference_station", "reference_distance_km", "window",
    "time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m", "missed_events", "extra_events"];
const PREVIOUS = ["time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m", "missed_events", "extra_events"];
const OFFSETS = ["reference_station_id", "time_offset_high_min", "time_offset_low_min", "height_offset_high",
    "height_offset_low", "height_adjusted_type", "licence_id"];
const TOMBSTONE = ["station_id", "name", "status", "removed_in", "removed_reason"];

function iso(t) {
    if (t == null) return null;
    return t.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function encStation(s) {
    if (s == null) return null;
    const rec = s.recommendedSet;
    return {
        station_id: s.station_id, name: s.name, country: s.country, lat: s.lat, lon: s.lon, type: s.type,
        kind: s.kind, timezone: s.timezone, aliases: s.aliases, status: s.status,
        is_reference: s.isReference, is_subordinate: s.isSubordinate, is_tide: s.isTide, is_current: s.isCurrent,
        recommended_set_id: rec ? rec.set_id : null,
    };
}

function encSet(cs) {
    if (cs == null) return null;
    const span = cs.record_span;
    const datum = cs.datum;
    return {
        set_id: cs.set_id, source: cs.source, source_type: cs.source_type, quantity: cs.quantity,
        source_record_id: cs.source_record_id, source_version: cs.source_version,
        record_span: span == null ? null : { start: iso(span.start), end: iso(span.end), good_samples: span.good_samples },
        datum: datum == null ? null : { msl_offset_m: datum.msl_offset_m, named: datum.named },
        qc_status: cs.qc_status,
        qc_flags: cs.qc_flags.map((f) => ({ flag: f.flag, verdict: f.verdict, values: f.values })),
        dropped_constituents: cs.dropped_constituents.map((d) => ({ name: d.name, dropped_reason: d.dropped_reason, detail: d.detail })),
        is_recommended: cs.isRecommended,
        convention_id: cs.convention.convention_id, licence_id: cs.licence.licence_id,
        constituent_count: cs.constituents.length,
    };
}

function encValidation(v) {
    const out = pick(v, VALIDATION);
    out.previous_release = v.previous_release == null ? null : pick(v.previous_release, PREVIOUS);
    return out;
}

function encFiles(files) {
    return [...files].map((f) => ({ name: f.name, url: f.url, size: f.size, sha256: f.sha256 }))
        .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

function encInfo(i) {
    if (i == null) return null;
    return { datestamp: i.datestamp, format_version: i.format_version, doi: i.doi, files: encFiles(i.files) };
}

function encStats(s) {
    return { type: s.type, kind: s.kind, country: s.country, source: s.source, qc_status: s.qc_status };
}

const ERROR_FIELDS = ["url", "status", "file", "expected", "actual", "path"];

export function makeRunner(sdk) {
    const state = { client: null, held: {} };

    const client = () => {
        if (!state.client) throw new Error("no client is open");
        return state.client;
    };
    // R: the held release named by `on`, or the client (which forwards to its current release).
    const target = (msg) => (msg.on ? state.held[msg.on] : client());
    const release = (msg) => (msg.on ? state.held[msg.on] : client().release);
    const lookStation = (msg, a) => target(msg).station(a.station_id);
    const lookSet = (msg, a) => {
        const st = lookStation(msg, a);
        return st ? st.constantSet(a.set_id) : null;
    };

    const ops = {
        async open(a) {
            if (state.client) {
                await state.client.close();
                state.client = null;
            }
            const o = opts(a, ["release", "file", "cache_dir", "offline", "mode", "base_url", "timeout", "proxy", "ca_file",
                "user_agent", "on_network_error", "auto_update", "update_interval", "verify_on_open"]);
            state.client = await sdk.OpenTideConstants.open(o);
            const r = state.client.release;
            return { loaded_from: state.client.loadedFrom, datestamp: r.datestamp, format_version: r.format_version };
        },
        async close() {
            if (state.client) await state.client.close();
            state.client = null;
            return {};
        },
        hold_release(a) {
            state.held[a.name] = client().release;
            return {};
        },
        loaded_from: () => ({ loaded_from: client().loadedFrom }),
        last_error: () => ({ code: client().lastError ? client().lastError.code : null }),
        release_metadata(a, msg) {
            const r = release(msg);
            return {
                datestamp: r.datestamp, created: iso(r.created), format_version: r.format_version, doi: r.doi,
                concept_doi: r.concept_doi, source_versions: r.source_versions, build_commit: r.build_commit,
                changelog_url: r.changelog_url,
            };
        },
        release_files: (a, msg) => ({ files: encFiles(release(msg).files) }),
        releases: async () => ({ releases: (await client().releases()).map(encInfo) }),
        latest: async () => ({ release: encInfo(await client().latest()) }),
        check_for_update: async () => ({ release: encInfo(await client().checkForUpdate()) }),
        async update() {
            const u = await client().update();
            return { updated: u.updated, from: u.from, to: u.to };
        },
        async download(a) {
            const paths = await client().download(opts(a, ["release", "to", "formats", "overwrite"]));
            return { paths: paths.map(basename).sort() };
        },
        verify: async () => ({ verified: await client().verify() }),
        cached_releases: () => ({ datestamps: client().cachedReleases() }),
        prune: (a) => ({ removed: client().prune(opts(a, ["keep"])) }),
        station_count: (a, msg) => ({ station_count: release(msg).stationCount }),
        tombstone_count: (a, msg) => ({ tombstone_count: release(msg).tombstoneCount }),
        stats: (a, msg) => ({ stats: encStats(release(msg).stats) }),
        constituent_names: (a, msg) => ({ names: [...release(msg).constituentNames] }),
        conventions: (a, msg) => ({ conventions: release(msg).conventions.map((c) => pick(c, CONVENTION)) }),
        convention(a, msg) {
            const c = release(msg).convention(a.convention_id);
            return { convention: c ? pick(c, CONVENTION) : null };
        },
        licences: (a, msg) => ({ licences: release(msg).licences.map((l) => pick(l, LICENCE)) }),
        licence(a, msg) {
            const l = release(msg).licence(a.licence_id);
            return { licence: l ? pick(l, LICENCE) : null };
        },
        citation: (a, msg) => ({ citation: release(msg).citation }),
        attribution(a, msg) {
            const t = target(msg);
            if (!Object.prototype.hasOwnProperty.call(a, "station_ids")) return { attribution: t.attribution() };
            const stations = a.station_ids.map((id) => t.station(id));
            return { attribution: t.attribution(stations) };
        },
        station: (a, msg) => ({ station: encStation(target(msg).station(a.station_id)) }),
        require_station: (a, msg) => ({ station: encStation(target(msg).requireStation(a.station_id)) }),
        tombstone(a, msg) {
            const t = target(msg).tombstone(a.station_id);
            return { tombstone: t ? pick(t, TOMBSTONE) : null };
        },
        station_by_alias(a, msg) {
            const s = target(msg).stationByAlias(a.system, a.alias_id);
            return { station_id: s ? s.station_id : null };
        },
        stations: (a, msg) => ({ station_ids: target(msg).stations(opts(a, FILTERS)).map((s) => s.station_id) }),
        iter_stations: (a, msg) => ({ station_ids: [...target(msg).iterStations(opts(a, FILTERS))].map((s) => s.station_id) }),
        search: (a, msg) => ({ station_ids: target(msg).search(opts(a, ["name", "limit", "match", ...FILTERS])).map((s) => s.station_id) }),
        near(a, msg) {
            const hits = target(msg).near(opts(a, ["lat", "lon", "radius_km", "limit", ...FILTERS]));
            return { station_ids: hits.map((h) => h.station.station_id), distance_km: hits.map((h) => h.distance_km) };
        },
        nearest(a, msg) {
            const h = target(msg).nearest(opts(a, ["lat", "lon", "max_km", ...FILTERS]));
            return h ? { station_id: h.station.station_id, distance_km: h.distance_km } : { station_id: null, distance_km: null };
        },
        reference_station(a, msg) {
            const st = lookStation(msg, a);
            const ref = st ? target(msg).referenceStation(st) : null;
            return { station_id: ref ? ref.station_id : null };
        },
        subordinates_of(a, msg) {
            const st = lookStation(msg, a);
            return { station_ids: st ? target(msg).subordinatesOf(st).map((s) => s.station_id) : [] };
        },
        station_validation(a, msg) {
            const st = lookStation(msg, a);
            return { validation: st ? st.validation.map(encValidation) : [] };
        },
        subordinate_offsets(a, msg) {
            const st = lookStation(msg, a);
            const off = st ? st.subordinateOffsets : null;
            return { offsets: off ? pick(off, OFFSETS) : null };
        },
        recommended_set(a, msg) {
            const st = lookStation(msg, a);
            const rs = st ? st.recommendedSet : null;
            return { set_id: rs ? rs.set_id : null };
        },
        constant_sets(a, msg) {
            const st = lookStation(msg, a);
            return { set_ids: st ? st.constantSets(opts(a, ["include_excluded"])).map((c) => c.set_id) : [] };
        },
        constant_set: (a, msg) => ({ set: encSet(lookSet(msg, a)) }),
        constituents(a, msg) {
            const cs = lookSet(msg, a);
            return { constituents: cs ? cs.constituents.map((c) => pick(c, CONSTITUENT)) : [] };
        },
        constituent(a, msg) {
            const cs = lookSet(msg, a);
            const c = cs ? cs.constituent(a.name) : null;
            return { constituent: c ? pick(c, CONSTITUENT) : null };
        },
        provenance(a, msg) {
            const cs = lookSet(msg, a);
            const p = cs ? cs.provenance : null;
            return p ? { provenance: pick(p, PROVENANCE), raw: p.raw } : { provenance: null, raw: null };
        },
        set_validation(a, msg) {
            const cs = lookSet(msg, a);
            return { validation: cs ? cs.validation.map(encValidation) : [] };
        },
        raw(a, msg) {
            let obj = null;
            switch (a.object) {
                case "station": obj = lookStation(msg, a); break;
                case "tombstone": obj = target(msg).tombstone(a.station_id); break;
                case "set": obj = lookSet(msg, a); break;
                case "constituent": { const cs = lookSet(msg, a); obj = cs ? cs.constituent(a.name) : null; break; }
                case "convention": obj = release(msg).convention(a.convention_id); break;
                case "licence": obj = release(msg).licence(a.licence_id); break;
                default: throw new Error(`unknown raw object ${a.object}`);
            }
            return { raw: obj ? obj.raw : null };
        },
    };

    async function handle(msg) {
        const fn = ops[msg.op];
        try {
            if (!fn) throw new Error(`unknown op ${msg.op}`);
            const result = await fn(msg.args || {}, msg);
            return { ok: true, result };
        } catch (e) {
            if (typeof sdk.OpenTideConstantsError === "function" && e instanceof sdk.OpenTideConstantsError) {
                const fields = {};
                for (const f of ERROR_FIELDS) if (e[f] !== undefined && e[f] !== null) fields[f] = e[f];
                return { ok: false, error: { code: e.code, message: String(e.message), fields } };
            }
            const name = e && e.constructor ? e.constructor.name : typeof e;
            return { ok: false, error: { code: `uncaught:${name}`, message: String(e && e.stack ? e.stack : e) } };
        }
    }

    async function shutdown() {
        if (state.client) {
            try { await state.client.close(); } catch { /* the runner is exiting */ }
            state.client = null;
        }
    }

    return { handle, shutdown };
}
