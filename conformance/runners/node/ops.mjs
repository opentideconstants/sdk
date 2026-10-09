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

// A field the op needs: undefined means the SDK does not have it, which fails the step.
function need(obj, field) {
    if (obj[field] === undefined) throw new Error(`the SDK has no ${field}`);
    return obj[field];
}

// Every field must be there: a field the SDK leaves undefined fails the step (need). Only a missing parent object
// gives nulls.
const pick = (obj, fields) => {
    const out = {};
    for (const f of fields) out[f] = obj == null ? null : need(obj, f);
    return out;
};

const CONSTITUENT = ["name", "source_name", "doodson", "speed_deg_per_hour", "amplitude_m", "phase_deg",
    "amp_uncertainty_m", "phase_uncertainty_deg", "kept_reason"];
const CONVENTION = ["convention_id", "phase_reference", "utc_offset_hours", "v0_model", "nodal_handling",
    "nodal_formula_ids", "constituent_table_version", "tables_sha256", "canary"];
const LICENCE = ["licence_id", "spdx", "provider", "citation", "attribution", "url"];
const PROVENANCE = ["adapter_version", "input_sha256", "selection_reason", "decision", "carried_from_release"];
const VALIDATION = ["set_id", "reference_source", "reference_station", "reference_distance_km", "window",
    "time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m", "missed_events", "extra_events"];
const PREVIOUS = ["time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m", "missed_events", "extra_events"];
const OFFSETS = ["reference_station_id", "time_offset_high_min", "time_offset_low_min", "height_offset_high",
    "height_offset_low", "height_adjusted_type", "licence_id"];
const TOMBSTONE = ["station_id", "name", "status", "removed_in", "removed_reason", "merged_into", "detail"];

function iso(t) {
    if (t == null) return null;
    return t.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function encStation(s) {
    if (s == null) return null;
    const rec = need(s, "recommendedSet");
    return {
        station_id: s.station_id, name: s.name, country: s.country, lat: s.lat, lon: s.lon, type: s.type,
        kind: s.kind, timezone: s.timezone, aliases: s.aliases, status: s.status,
        is_reference: s.isReference, is_subordinate: s.isSubordinate, is_tide: s.isTide, is_current: s.isCurrent,
        recommended_set_id: rec ? rec.set_id : null,
    };
}

function encSet(cs) {
    if (cs == null) return null;
    const span = need(cs, "record_span");
    const datum = need(cs, "datum");
    return {
        set_id: cs.set_id, source: cs.source, source_type: cs.source_type, quantity: cs.quantity,
        source_record_id: cs.source_record_id, source_version: cs.source_version,
        record_span: span === null ? null : { start: iso(need(span, "start")), end: iso(need(span, "end")), good_samples: need(span, "good_samples") },
        datum: datum === null ? null : { msl_offset_m: need(datum, "msl_offset_m"), named: need(datum, "named") },
        qc_status: cs.qc_status,
        qc_flags: cs.qc_flags.map((f) => pick(f, ["flag", "reason", "values"])),
        dropped_constituents: cs.dropped_constituents.map((d) => pick(d, ["name", "dropped_reason", "detail"])),
        time_base: encTimeBase(need(cs, "time_base")),
        is_recommended: cs.isRecommended,
        convention_id: need(need(cs, "convention"), "convention_id"), licence_id: need(need(cs, "licence"), "licence_id"),
        constituent_count: cs.constituents.length,
    };
}

function encValidation(v) {
    const out = pick(v, VALIDATION);
    const prev = need(v, "previous_release");
    out.previous_release = prev === null ? null : pick(prev, PREVIOUS);
    return out;
}

function encFiles(files) {
    return [...files].map((f) => pick(f, ["name", "url", "size", "sha256"]))
        .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

function encInfo(i) {
    if (i == null) return null;
    return {
        datestamp: need(i, "datestamp"), format_version: need(i, "format_version"), concept_doi: need(i, "concept_doi"),
        zenodo_version_doi: need(i, "zenodo_version_doi"), content_sha256: need(i, "content_sha256"),
        files: encFiles(need(i, "files")),
    };
}


function encBuild(b) {
    if (b == null) return null;
    return {
        build_commit: need(b, "build_commit"), built_at: iso(need(b, "built_at")), fetched_at: iso(need(b, "fetched_at")),
        run_id: need(b, "run_id"), tool_versions: need(b, "tool_versions"),
    };
}


const EVIDENCE = ["comparator_kind", "comparator_id", "distance_km", "lag_min", "detail"];

// Encode what the SDK returns: a plain object with its own keys (a missing key is not filled in), or a typed
// object field by field, each through need().
function asReturned(v, fields) {
    if (v == null) return null;
    const proto = Object.getPrototypeOf(v);
    if (proto === Object.prototype || proto === null) return { ...v };
    const out = {};
    for (const f of fields) out[f] = need(v, f);
    return out;
}

// TimeBase: typed fields; correction is an object {from, to} or null; evidence is a list of objects.
function encTimeBase(t) {
    if (t == null) return null;
    const corr = need(t, "correction");
    return {
        code: need(t, "code"), reason: need(t, "reason"), declared: need(t, "declared"), published: need(t, "published"),
        correction: asReturned(corr, ["from", "to"]),
        months_dropped: [...need(t, "months_dropped")], decided_in: need(t, "decided_in"),
        decided_build_commit: need(t, "decided_build_commit"),
        evidence: [...need(t, "evidence")].map((e) => asReturned(e, EVIDENCE)),
    };
}

function encStats(s) {
    return pick(s, ["type", "kind", "country", "source", "qc_status"]);
}

// The result as strict JSON: NaN is null (README "Result encodings"); an infinite number cannot be encoded
// (JSON.stringify would print null and hide it).
function finite(v) {
    if (typeof v === "number") {
        if (Number.isNaN(v)) return null;
        if (!Number.isFinite(v)) throw new RangeError(`the SDK returned ${v}, which JSON cannot carry`);
        return v;
    }
    if (typeof v === "bigint" || typeof v === "symbol" || typeof v === "function") {
        throw new TypeError(`the runner cannot encode a ${typeof v} as JSON`);
    }
    // a value the SDK left out: JSON.stringify would drop the key, or write null in a list; fail the step instead
    if (v === undefined) throw new TypeError("the SDK gave no value (undefined)");
    // a list element that is missing (a hole) is undefined too, so map over every index, not with Array.map
    if (Array.isArray(v)) return Array.from(v, finite);
    if (v !== null && typeof v === "object") {
        // only a plain object is encoded key by key; anything else (a Map, a Set, a Date, a class instance, a Promise)
        // JSON.stringify would write as {} or a string, hiding what the SDK returned
        if (![Object.prototype, null].includes(Object.getPrototypeOf(v))) {
            throw new TypeError(`the runner cannot encode a ${v.constructor ? v.constructor.name : "object"} as JSON`);
        }
        const out = {};
        for (const [k, x] of Object.entries(v)) {
            try {
                out[k] = finite(x);
            } catch (e) {
                e.message = `${k}: ${e.message}`;
                throw e;
            }
        }
        return out;
    }
    return v;
}

const ERROR_FIELDS = ["url", "status", "file", "expected", "actual", "path", "removed"];

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
                datestamp: need(r, "datestamp"), created: iso(need(r, "created")), format_version: need(r, "format_version"),
                concept_doi: need(r, "concept_doi"), source_versions: need(r, "source_versions"), build_commit: need(r, "build_commit"),
                changelog_url: need(r, "changelog_url"), zenodo_version_doi: need(r, "zenodo_version_doi"),
            };
        },
        release_files: (a, msg) => ({ files: encFiles(release(msg).files) }),
        releases: async () => ({ releases: (await client().releases()).map(encInfo) }),
        latest: async () => ({ release: encInfo(await client().latest()) }),
        check_for_update: async () => ({ release: encInfo(await client().checkForUpdate()) }),
        newer_format_major: () => ({ newer_format_major: need(client(), "newerFormatMajor") }),
        async update() {
            const u = await client().update();
            return pick(u, ["updated", "from", "to"]);
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
        // station_id null goes to the SDK as null, and station_on looks the station up in a held release (a foreign
        // Station): both must be invalid_argument (CR2 DR24)
        reference_station(a, msg) {
            const passed = a.station_id === null || "station_on" in a;
            const st = a.station_id === null ? null : ("station_on" in a ? state.held[a.station_on] : target(msg)).station(a.station_id);
            if (!st && !passed) return { station_id: null };
            const ref = target(msg).referenceStation(st);
            return { station_id: ref ? ref.station_id : null };
        },
        subordinates_of(a, msg) {
            const passed = a.station_id === null || "station_on" in a;
            const st = a.station_id === null ? null : ("station_on" in a ? state.held[a.station_on] : target(msg)).station(a.station_id);
            if (!st && !passed) return { station_ids: null };
            return { station_ids: target(msg).subordinatesOf(st).map((s) => s.station_id) };
        },
        station_validation(a, msg) {
            const st = lookStation(msg, a);
            return { validation: st ? need(st, "validation").map(encValidation) : null };
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
            return { set_ids: st ? st.constantSets(opts(a, ["include_no_constants"])).map((c) => c.set_id) : null };
        },
        constant_set: (a, msg) => ({ set: encSet(lookSet(msg, a)) }),
        constituents(a, msg) {
            const cs = lookSet(msg, a);
            return { constituents: cs ? need(cs, "constituents").map((c) => pick(c, CONSTITUENT)) : null };
        },
        constituent(a, msg) {
            const cs = lookSet(msg, a);
            const c = cs ? cs.constituent(a.name) : null;
            return { constituent: c ? pick(c, CONSTITUENT) : null };
        },
        provenance(a, msg) {
            const cs = lookSet(msg, a);
            const p = cs ? cs.provenance : null;
            return p ? { provenance: { ...pick(p, PROVENANCE), build: encBuild(need(p, "build")) }, raw: p.raw }
                : { provenance: null, raw: null };
        },
        set_validation(a, msg) {
            const cs = lookSet(msg, a);
            return { validation: cs ? need(cs, "validation").map(encValidation) : null };
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
            const result = finite(await fn(msg.args || {}, msg));
            return { ok: true, result };
        } catch (e) {
            if (e instanceof sdk.OpenTideConstantsError) {
                try {
                    return encodeSdkError(e);
                } catch (x) { // an error while encoding the SDK error is still one reply
                    return { ok: false, error: { code: `uncaught:${x && x.constructor ? x.constructor.name : typeof x}`, message: `cannot encode the SDK error: ${x}` } };
                }
            }
            const name = e && e.constructor ? e.constructor.name : typeof e;
            return { ok: false, error: { code: `uncaught:${name}`, message: String(e && e.stack ? e.stack : e) } };
        }
    }

    function encodeSdkError(e) {
        const fields = {};
        for (const f of ERROR_FIELDS) if (e[f] !== undefined && e[f] !== null) fields[f] = e[f];
        let code = e.code;
        if (e.tombstone != null) {
            // a tombstone the runner cannot encode fails the step (the code too, so a code-only check fails)
            try { fields.tombstone = pick(e.tombstone, TOMBSTONE); } catch (te) {
                code = fields.tombstone = `uncaught:${te && te.constructor ? te.constructor.name : typeof te}`;
            }
        }
        return { ok: false, error: { code, message: String(e.message), fields: finite(fields) } };
    }

    // Closes the client at shutdown. Returns false (and the runner exits non-zero) when close() fails.
    async function shutdown() {
        if (!state.client) return true;
        try {
            await state.client.close();
            return true;
        } catch (e) {
            const text = `close failed at shutdown: ${e && e.stack ? e.stack : e}`;
            if (globalThis.process && globalThis.process.stderr) globalThis.process.stderr.write(text + "\n");
            else console.error(text);
            return false;
        } finally {
            state.client = null;
        }
    }

    return { handle, shutdown };
}
