import * as native from "../src/canonical.js";
import type * as C from "../src/canonical-types.js";
import { releaseFromJson } from '../src/loader.js';
import { indexDoc, parseHeader, predictionAstroTable } from '../src/release.js';
import { InvalidArgumentError, OpenTideConstantsError } from '../src/errors.js';

const migrated = new Set(['B01', 'B02', 'B03', 'B04', 'B07', 'B08.raw', 'B24', 'B28', 'B39', 'B41', 'B42', 'B43.roots', 'B44.roots']);
interface EntryObservation { readonly id: string; readonly refusal?: string; readonly value_json?: string; readonly error_json?: string; readonly argument_json: string; readonly cleanup_observed: boolean }
async function invoke<Result>(id: string, call: () => Result | Promise<Result>, argumentJson: string): Promise<EntryObservation> {
    try {
        const value = await call();
        if (migrated.has(id)) return { id, value_json: JSON.stringify(value) ?? 'null', argument_json: argumentJson, cleanup_observed: true };
        throw new Error(`Private seam ${id} fabricated a successful value`);
    } catch (error) {
        if (id === 'B04' && error instanceof Error && !(error instanceof native.CanonicalUnimplementedError)) return { id, error_json: JSON.stringify({ code: error instanceof OpenTideConstantsError ? error.code : 'native_exception', structured_fields: { message: error.message }, cause: error.cause ?? null }), argument_json: argumentJson, cleanup_observed: true };
        if (!(error instanceof native.CanonicalUnimplementedError) || error.behavior !== id) throw error;
        return { id, refusal: error.message, argument_json: argumentJson, cleanup_observed: true };
    }
}
export async function exerciseShape(source: string, profile: 'typescript_node' | 'typescript_browser', predictionSource: string) {
    const release = releaseFromJson(new TextEncoder().encode(source), []);
    const predictionRelease = releaseFromJson(new TextEncoder().encode(predictionSource), []);
    const station = release.requireStation('OTC-T-0001');
    const constants = station.constantSets()[0];
    if (!constants) throw new Error('Required real constant-set owner missing');
    const sourceRecord = { raw: station.raw };
    const origin = Symbol('inert construction origin');
    const fieldProjection = {"scalar_types":"Exact original canonical field table attached per member; known wrong type is invalid_release, absent nullable is null, missing arrays use each attached contract default. Raw fields preserve source JSON without computed fields.","models":"Model IDs refer to B07, source/ownership objects also B08, historical fields B36, prediction/local/datum results B48. These are value projection behaviors, not an assertion that every getter has an independent algorithm.","subordinate_offsets":"Complete source object, including all unknown nested fields, represented by tolerant cache-specific definitions derived from accepted schema33a760ad. Known primitive types, required historical fields, source binding conditions and raw values remain unchanged.","scope":"25 scenario families enumerate required shared branches. They are not 25 executed passes or exhaustive binary-branch verification. Each family expands to its incorporated original case table and required additional guard-reaching witnesses.","fallback":"Complete actual fallback object, including unknown nested fields. String reasons remain source strings in cache/raw and become typed other when unknown. Cache-source comparison includes every preserved field, not only current known keys."} as const;
    const values: { operation: C.operation; arguments: C.arguments; member_contract: C.member_contract; explicit_options: C.explicit_options; environment: C.environment; platform_defaults: C.platform_defaults; ordered_failures: C.ordered_failures; cause: C.cause; canonical_result: C.canonical_result; canonical_error: C.canonical_error; native_profile: C.native_profile; source_bytes: C.source_bytes; reader_version: C.reader_version; document_kind: C.document_kind; parsed_document: C.parsed_document; required_links: C.required_links; raw_fields: C.raw_fields; field_contract: C.field_contract; origin: C.origin; model_type: C.model_type; access_kind: C.access_kind; source_record: C.source_record; station: C.station; release_origin: C.release_origin; cache_state: C.cache_state; clock: C.clock; release_request: C.release_request; effective_options: C.effective_options; metadata_request: C.metadata_request; trusted_cache: C.trusted_cache; transport_options: C.transport_options; client_state: C.client_state; update_request: C.update_request; query_kind: C.query_kind; held_release: C.held_release; query_arguments: C.query_arguments; resource_state: C.resource_state; lifetime_action: C.lifetime_action; checksum_bytes: C.checksum_bytes; pointer_digests: C.pointer_digests; required_files: C.required_files; acquisition_descriptor: C.acquisition_descriptor; load_mode: C.load_mode; locked_cache_state: C.locked_cache_state; verified_file_rows: C.verified_file_rows; release_metadata: C.release_metadata; release_candidates: C.release_candidates; release_files: C.release_files; trusted_cached_pointer: C.trusted_cached_pointer; destination: C.destination; format_selection: C.format_selection; overwrite_policy: C.overwrite_policy; inventory_action: C.inventory_action; keep: C.keep; current_cache_directory: C.current_cache_directory; io_kind: C.io_kind; io_request: C.io_request; io_options: C.io_options; station_source_row: C.station_source_row; source_byte_span: C.source_byte_span; projection_contract: C.projection_contract; source_files: C.source_files; supplied_index: C.supplied_index; index_presence: C.index_presence; index_entry: C.index_entry; stream_reader: C.stream_reader; station_id: C.station_id; cache_document: C.cache_document; release_view: C.release_view; identity_query: C.identity_query; station_sets: C.station_sets; original_recommendation: C.original_recommendation; commercial_only: C.commercial_only; candidate_path: C.candidate_path; include_flagged: C.include_flagged; include_fallback: C.include_fallback; commercial_basis: C.commercial_basis; path_request: C.path_request; query_options: C.query_options; summary_kind: C.summary_kind; summary_options: C.summary_options; own_offset: C.own_offset; reference_path: C.reference_path; historical_policy: C.historical_policy; selection_kind: C.selection_kind; published_metadata: C.published_metadata; citation_style: C.citation_style; time_inputs: C.time_inputs; window_inputs: C.window_inputs; step: C.step; local_time_profile: C.local_time_profile; station_request: C.station_request; selection_options: C.selection_options; selected_prediction_model: C.selected_prediction_model; utc_instant: C.utc_instant; prediction_instants: C.prediction_instants; requested_datum: C.requested_datum; prediction_window: C.prediction_window; current_request: C.current_request; current_operation: C.current_operation; tide_request: C.tide_request; reference_model: C.reference_model; own_current_offsets: C.own_current_offsets; auxiliary_kind: C.auxiliary_kind; auxiliary_operation: C.auxiliary_operation; source_values: C.source_values; result_context: C.result_context; result_values: C.result_values; utc_result: C.utc_result; auxiliary_member_id: C.auxiliary_member_id; lock_request: C.lock_request; lock_state: C.lock_state; http_request: C.http_request; include_no_constants: C.include_no_constants } = {
        operation: "astro_table",
        arguments: { member_id: "Client.close", arguments: {} },
        member_contract: { member_id: "Client.close", arguments: {} },
        explicit_options: { member_id: "Client.open" },
        environment: {},
        platform_defaults: { member_id: "Client.open" },
        ordered_failures: [],
        cause: null,
        canonical_result: { presence: 'present_value', binding: { member_id: 'Station.raw', value: station.raw } },
        canonical_error: { code: "invalid_argument", structured_fields: {}, cause: null },
        native_profile: profile,
        source_bytes: new Uint8Array(),
        reader_version: { major: 0, minor: 0 },
        document_kind: "release",
        parsed_document: { variant: "station_row", value: station.raw },
        required_links: [],
        raw_fields: station.raw,
        field_contract: { model_type: "Station", fields: [] },
        origin: origin,
        model_type: "Client",
        access_kind: "raw_record",
        source_record: sourceRecord.raw,
        station: station,
        release_origin: origin,
        cache_state: { cache_root: "inert-cache", release_candidates: [], pointer_cache: null, lock_state: { cache_root: "inert-cache", owner: null, held_token: null } },
        clock: 0,
        release_request: "latest",
        effective_options: { member_id: "Client.open" },
        metadata_request: { request_url: "construction", document_kind: "construction" },
        trusted_cache: null,
        transport_options: { member_id: "Client.open" },
        client_state: { current_release: release, effective_options: { member_id: "Client.open" }, cache_state: { cache_root: "inert-cache", release_candidates: [], pointer_cache: null, lock_state: { cache_root: "inert-cache", owner: null, held_token: null } }, last_error: null, last_update_check: null, closed: false },
        update_request: { request_url: "construction", document_kind: "construction" },
        query_kind: "stations",
        held_release: release,
        query_arguments: { member_id: "Client.close", arguments: {} },
        resource_state: { current_release: release, effective_options: { member_id: "Client.open" }, cache_state: { cache_root: "inert-cache", release_candidates: [], pointer_cache: null, lock_state: { cache_root: "inert-cache", owner: null, held_token: null } }, last_error: null, last_update_check: null, closed: false },
        lifetime_action: "construction",
        checksum_bytes: new Uint8Array(),
        pointer_digests: {},
        required_files: [],
        acquisition_descriptor: { datestamp: "construction", files: [], checksum_bytes: null, pointer_digests: {}, required_file_request: null, metadata: {} },
        load_mode: "eager",
        locked_cache_state: { cache_root: "inert-cache", release_candidates: [], pointer_cache: null, lock_state: { cache_root: "inert-cache", owner: null, held_token: null } },
        verified_file_rows: [],
        release_metadata: {},
        release_candidates: [],
        release_files: release.files,
        trusted_cached_pointer: null,
        destination: "inert-cache",
        format_selection: { formats: [], required_files: [] },
        overwrite_policy: { to: "inert-destination" },
        inventory_action: "list",
        keep: 0,
        current_cache_directory: "inert-cache",
        io_kind: "lock",
        io_request: { variant: "lock", value: { directory: "inert-cache", operation: "take", token: null } },
        io_options: { variant: "lock", value: { cache_root: "inert-cache", owner: null, held_token: null } },
        station_source_row: station.raw,
        source_byte_span: { offset_bytes: 0, length_bytes: 0 },
        projection_contract: fieldProjection,
        source_files: { jsonl: "inert-cache", meta: "inert-cache", jsonl_sha256: "construction", jsonl_size: 0, meta_sha256: "construction", meta_size: 0 },
        supplied_index: null,
        index_presence: {},
        index_entry: { "station_id": "construction", "status": "construction", "name": null, "name_folded": null, "country": null, "type": null, "kind": null, "reference_station_id": null, "offsets_licence_id": null, "recommended_set_id": null, "lat": null, "lon": null, "offset": 0, "length": 0, "aliases": {  }, "sets": [], "subordinate_offsets": null, "current_offsets": [] },
        stream_reader: { release_view: release, file_descriptor: 0, index: {}, index_presence: {}, station_lru: {}, closed: false },
        station_id: "construction",
        cache_document: { variant: "stream_index", value: { "index_version": 1, "discovery_index_version": 1, "datestamp": "construction", "jsonl": "construction", "jsonl_sha256": "construction", "jsonl_size": 0, "by": "construction", "stations": [] } },
        release_view: release,
        identity_query: "construction",
        station_sets: [],
        original_recommendation: null,
        commercial_only: false,
        candidate_path: { variant: "direct", station: station, constant_set: constants, release_view: release },
        include_flagged: false,
        include_fallback: false,
        commercial_basis: "strict",
        path_request: "construction",
        query_options: { member_id: "Release.stations" },
        summary_kind: "stats",
        summary_options: { original_recommendation: null, commercial_only: false, include_no_constants: false },
        own_offset: null,
        reference_path: { station: station, release_view: release, constant_set: null, own_offset: null, reference_bin: null },
        historical_policy: "fallback",
        selection_kind: "discovery",
        published_metadata: { contributors: {}, year: 0, concept_doi: null, zenodo_version_doi: null, dataset_url: "construction" },
        citation_style: "construction",
        time_inputs: { member_id: "Client.close", arguments: {} },
        window_inputs: { member_id: "Client.close", arguments: {} },
        step: 0,
        local_time_profile: { tz: "UTC" },
        station_request: station,
        selection_options: { member_id: "Release.heights" },
        selected_prediction_model: { station: station, release_view: release, constant_set: constants, convention: constants.convention, astro_table: {}, required_constituents: [], reference_bin: null, mean_term: 0, datum_source: null },
        utc_instant: 0,
        prediction_instants: [],
        requested_datum: "construction",
        prediction_window: { start: 0, stop: 0, step: null },
        current_request: { member_id: "Client.close", arguments: {} },
        current_operation: "currents",
        tide_request: { member_id: "Client.close", arguments: {} },
        reference_model: { station: station, release_view: release, constant_set: constants, convention: constants.convention, astro_table: {}, required_constituents: [], reference_bin: null, mean_term: 0, datum_source: null },
        own_current_offsets: null,
        auxiliary_kind: "model_access",
        auxiliary_operation: "astro_table",
        source_values: { variant: "requires_model", station_request: station, release_view: release, selection_options: { member_id: "Release.heights" }, utc_instant: null },
        result_context: { station_id: "construction", set_id: null, reference_station_id: null, bin_number: null, datum: null, release_datestamp: "construction", algorithm: "construction" },
        result_values: { member_id: "Station.raw", value: station.raw },
        utc_result: { member_id: "Station.raw", value: station.raw },
        auxiliary_member_id: "Client.open",
        lock_request: { directory: "inert-cache", operation: "take", token: null },
        lock_state: { cache_root: "inert-cache", owner: null, held_token: null },
        http_request: { url: "construction", conditional_etag: null },
        include_no_constants: false,
    };
    const header = parseHeader(release._header);
    const nativeIndex = indexDoc(station.raw, header, 0, 0,
        new Set(header.conventions.map(row => String(row['convention_id']))), new Set(header.licences.map(row => String(row['licence_id']))));
    values.field_contract = { model_type: 'Station', fields: ['Station.station_id', 'Station.raw'], native_owner: { release, entry: nativeIndex } };
    values.model_type = 'Station';
    values.projection_contract = { ...fieldProjection, native_header: header };
    const failure = new InvalidArgumentError('file cannot be combined with release, offline or onNetworkError');
    values.ordered_failures = [{ code: failure.code, structured_fields: { message: failure.message }, cause: null }];
    const node = profile === 'typescript_node' ? (await import('../src/node.js')).nodeApi : null;
    const platform = node ? node.nodePlatform() : (await import('../src/browser.js')).browserPlatform();
    values.platform_defaults = { member_id: 'Client.open', native_context: { platform, node: node ? { checkReadable: node.checkReadable, defaultCacheRoot: node.defaultCacheRoot } : null } };
    const predictionStation = predictionRelease.requireStation('OTC-P-0001');
    const predictionConstants = predictionStation.recommendedSet;
    const table = predictionAstroTable(predictionRelease);
    if (!predictionConstants || !table) throw new Error('Authentic native prediction context missing');
    values.selected_prediction_model = { station: predictionStation, release_view: predictionRelease, constant_set: predictionConstants,
        convention: predictionConstants.convention, astro_table: table._raw, required_constituents: predictionConstants.raw['constituents'] instanceof Array ? predictionConstants.raw['constituents'] : [], reference_bin: null, mean_term: 0, datum_source: predictionConstants.raw['datum'] ?? null };
    values.utc_instant = 1433116800.4369507;
    values.prediction_instants = [values.utc_instant, values.utc_instant];
    values.requested_datum = 'mean_level';
    values.prediction_window = { start: 1433116800, stop: 1433129714, step: null };
    values.time_inputs = { member_id: 'Release.heights', arguments: { station: predictionStation, start: new Date(1433116800000), stop: new Date(1433203200000) } };
    values.window_inputs = values.time_inputs;
    values.step = 600;
    const currentStation = predictionRelease.stations().find(row => row.kind === 'current' && Array.isArray(row.recommendedSet?.raw['current_bins']));
    const currentConstants = currentStation?.recommendedSet;
    if (!currentStation || !currentConstants) throw new Error('Authentic native current context missing');
    const currentTableId = currentConstants.convention.raw['astro_table_id'];
    const currentTable = await predictionRelease.astroTable(typeof currentTableId === 'string' ? currentTableId : null);
    if (!currentTable) throw new Error('Authentic selected native current table missing');
    const currentModel: C.selected_prediction_model = { ...values.selected_prediction_model, station: currentStation, constant_set: currentConstants, convention: currentConstants.convention, astro_table: currentTable._raw };
    const currentWindow: C.prediction_window = { start: Date.parse('2020-06-01T00:00:00Z') / 1000, stop: Date.parse('2020-06-02T00:00:00Z') / 1000, step: null };
    values.current_request = { member_id: 'Release.current_events', arguments: { station: currentStation, start: new Date(currentWindow.start * 1000), stop: new Date(currentWindow.stop * 1000) } };
    const runtime: EntryObservation[] = [];
    const call_actions: EntryObservation[] = [];
    try {
        runtime.push(await invoke("B01", () => native.validate_operation_arguments(values.operation, values.arguments, values.member_contract), JSON.stringify({ operation: values.operation, arguments: values.arguments, member_contract: values.member_contract })));
        runtime.push(await invoke("B02", () => native.resolve_effective_options(values.explicit_options, values.environment, values.platform_defaults), JSON.stringify({ explicit_options: values.explicit_options, environment: values.environment, platform_defaults: values.platform_defaults })));
        runtime.push(await invoke("B03", () => native.select_canonical_error(values.operation, values.ordered_failures, values.cause), JSON.stringify({ operation: values.operation, ordered_failures: values.ordered_failures, cause: values.cause })));
        runtime.push(await invoke("B04", () => native.translate_native_binding({ native_profile: profile, canonical_result: { presence: 'present_value', binding: { member_id: 'Station.raw', value: station.raw } } }), JSON.stringify({ native_profile: profile, canonical_result: values.canonical_result })));
        runtime.push(await invoke("B05", () => native.decode_release_document(values.source_bytes, values.reader_version, values.document_kind), JSON.stringify({ source_bytes: values.source_bytes, reader_version: values.reader_version, document_kind: values.document_kind })));
        runtime.push(await invoke("B06", () => native.validate_release_links(values.parsed_document, values.required_links), JSON.stringify({ parsed_document: values.parsed_document, required_links: values.required_links })));
        runtime.push(await invoke("B07", () => native.materialize_typed_model(values.raw_fields, values.field_contract, values.origin, values.model_type), JSON.stringify({ raw_fields: values.raw_fields, field_contract: values.field_contract, origin: values.origin, model_type: values.model_type })));
        runtime.push(await invoke("B08", () => native.access_raw_record(values.access_kind, values.source_record, values.station, values.release_origin, values.native_profile), JSON.stringify({ access_kind: values.access_kind, source_record: values.source_record, station: values.station, release_origin: values.release_origin, native_profile: values.native_profile })));
        runtime.push(await invoke("B09", () => native.open_client_release(values.arguments, values.environment, values.platform_defaults, values.cache_state, values.clock, values.native_profile, values.reader_version), JSON.stringify({ arguments: values.arguments, environment: values.environment, platform_defaults: values.platform_defaults, cache_state: values.cache_state, clock: values.clock, native_profile: values.native_profile, reader_version: values.reader_version })));
        runtime.push(await invoke("B10", () => native.resolve_release_request(values.release_request, values.effective_options, values.cache_state, values.clock, values.reader_version), JSON.stringify({ release_request: values.release_request, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock, reader_version: values.reader_version })));
        runtime.push(await invoke("B11", () => native.exchange_release_metadata(values.metadata_request, values.trusted_cache, values.transport_options, values.cache_state, values.clock, values.reader_version), JSON.stringify({ metadata_request: values.metadata_request, trusted_cache: values.trusted_cache, transport_options: values.transport_options, cache_state: values.cache_state, clock: values.clock, reader_version: values.reader_version })));
        runtime.push(await invoke("B12", () => native.update_client_release(values.client_state, values.update_request, values.clock, values.reader_version), JSON.stringify({ client_state: values.client_state, update_request: values.update_request, clock: values.clock, reader_version: values.reader_version })));
        runtime.push(await invoke("B13", () => native.refresh_client_if_due(values.client_state, values.query_kind, values.clock, values.reader_version), JSON.stringify({ client_state: values.client_state, query_kind: values.query_kind, clock: values.clock, reader_version: values.reader_version })));
        runtime.push(await invoke("B14", () => native.forward_held_release(values.held_release, values.query_arguments), JSON.stringify({ held_release: values.held_release, query_arguments: values.query_arguments })));
        runtime.push(await invoke("B15", () => native.enforce_resource_lifetime(values.resource_state, values.lifetime_action), JSON.stringify({ resource_state: values.resource_state, lifetime_action: values.lifetime_action })));
        runtime.push(await invoke("B16", () => native.bind_checksum_manifest(values.checksum_bytes, values.pointer_digests, values.required_files), JSON.stringify({ checksum_bytes: values.checksum_bytes, pointer_digests: values.pointer_digests, required_files: values.required_files })));
        runtime.push(await invoke("B17", () => native.acquire_release_files(values.acquisition_descriptor, values.effective_options, values.load_mode, values.cache_state, values.clock, values.reader_version), JSON.stringify({ acquisition_descriptor: values.acquisition_descriptor, effective_options: values.effective_options, load_mode: values.load_mode, cache_state: values.cache_state, clock: values.clock, reader_version: values.reader_version })));
        runtime.push(await invoke("B18", () => native.merge_cache_receipt(values.locked_cache_state, values.verified_file_rows, values.release_metadata), JSON.stringify({ locked_cache_state: values.locked_cache_state, verified_file_rows: values.verified_file_rows, release_metadata: values.release_metadata })));
        runtime.push(await invoke("B19", () => native.select_cached_release(values.release_candidates, values.effective_options, values.cache_state, values.clock), JSON.stringify({ release_candidates: values.release_candidates, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock })));
        runtime.push(await invoke("B20", () => native.verify_release_files(values.release_files, values.trusted_cached_pointer), JSON.stringify({ release_files: values.release_files, trusted_cached_pointer: values.trusted_cached_pointer })));
        runtime.push(await invoke("B21", () => native.publish_download(values.destination, values.format_selection, values.overwrite_policy, values.release_files, values.checksum_bytes, values.pointer_digests), JSON.stringify({ destination: values.destination, format_selection: values.format_selection, overwrite_policy: values.overwrite_policy, release_files: values.release_files, checksum_bytes: values.checksum_bytes, pointer_digests: values.pointer_digests })));
        runtime.push(await invoke("B22", () => native.manage_cache_inventory(values.inventory_action, values.cache_state, values.keep, values.current_cache_directory, values.clock), JSON.stringify({ inventory_action: values.inventory_action, cache_state: values.cache_state, keep: values.keep, current_cache_directory: values.current_cache_directory, clock: values.clock })));
        runtime.push(await invoke("B23", () => native.perform_guarded_io(values.io_kind, values.io_request, values.io_options, values.clock), JSON.stringify({ io_kind: values.io_kind, io_request: values.io_request, io_options: values.io_options, clock: values.clock })));
        runtime.push(await invoke("B24", () => native.project_station_index(values.station_source_row, values.source_byte_span, values.projection_contract), JSON.stringify({ station_source_row: values.station_source_row, source_byte_span: values.source_byte_span, projection_contract: values.projection_contract })));
        runtime.push(await invoke("B25", () => native.authenticate_station_index(values.source_files, values.supplied_index, values.index_presence, values.reader_version), JSON.stringify({ source_files: values.source_files, supplied_index: values.supplied_index, index_presence: values.index_presence, reader_version: values.reader_version })));
        runtime.push(await invoke("B26", () => native.compare_station_source(values.index_entry, values.station_source_row, values.index_presence), JSON.stringify({ index_entry: values.index_entry, station_source_row: values.station_source_row, index_presence: values.index_presence })));
        runtime.push(await invoke("B27", () => native.read_station_lazily(values.stream_reader, values.station_id, values.release_origin, values.reader_version), JSON.stringify({ stream_reader: values.stream_reader, station_id: values.station_id, release_origin: values.release_origin, reader_version: values.reader_version })));
        runtime.push(await invoke("B28", () => native.encode_cache_json(values.cache_document), JSON.stringify({ cache_document: values.cache_document })));
        runtime.push(await invoke("B29", () => native.lookup_station_identity(values.release_view, values.identity_query, values.reader_version), JSON.stringify({ release_view: values.release_view, identity_query: values.identity_query, reader_version: values.reader_version })));
        runtime.push(await invoke("B30", () => native.select_effective_recommendation(values.station_sets, values.original_recommendation, values.commercial_only), JSON.stringify({ station_sets: values.station_sets, original_recommendation: values.original_recommendation, commercial_only: values.commercial_only })));
        runtime.push(await invoke("B31", () => native.admit_quality_path(values.candidate_path, values.include_flagged, values.include_fallback), JSON.stringify({ candidate_path: values.candidate_path, include_flagged: values.include_flagged, include_fallback: values.include_fallback })));
        runtime.push(await invoke("B32", () => native.admit_commercial_path(values.candidate_path, values.commercial_only, values.commercial_basis), JSON.stringify({ candidate_path: values.candidate_path, commercial_only: values.commercial_only, commercial_basis: values.commercial_basis })));
        runtime.push(await invoke("B33", () => native.resolve_reference_path(values.station_source_row, values.path_request, values.release_view), JSON.stringify({ station_source_row: values.station_source_row, path_request: values.path_request, release_view: values.release_view })));
        runtime.push(await invoke("B34", () => native.execute_discovery_query(values.release_view, values.query_kind, values.query_options, values.reader_version), JSON.stringify({ release_view: values.release_view, query_kind: values.query_kind, query_options: values.query_options, reader_version: values.reader_version })));
        runtime.push(await invoke("B35", () => native.summarize_station_sets(values.summary_kind, values.release_view, values.station_sets, values.summary_options), JSON.stringify({ summary_kind: values.summary_kind, release_view: values.release_view, station_sets: values.station_sets, summary_options: values.summary_options })));
        runtime.push(await invoke("B36", () => native.admit_historical_offset(values.own_offset, values.reference_path, values.historical_policy, values.selection_kind, values.reader_version), JSON.stringify({ own_offset: values.own_offset, reference_path: values.reference_path, historical_policy: values.historical_policy, selection_kind: values.selection_kind, reader_version: values.reader_version })));
        runtime.push(await invoke("B37", () => native.format_attribution(values.station, values.release_view, values.commercial_only), JSON.stringify({ station: values.station, release_view: values.release_view, commercial_only: values.commercial_only })));
        runtime.push(await invoke("B38", () => native.format_citation(values.published_metadata, values.citation_style), JSON.stringify({ published_metadata: values.published_metadata, citation_style: values.citation_style })));
        runtime.push(await invoke("B39", () => native.parse_prediction_window(values.time_inputs, values.window_inputs, values.step, values.local_time_profile), JSON.stringify({ time_inputs: values.time_inputs, window_inputs: values.window_inputs, step: values.step, local_time_profile: values.local_time_profile })));
        runtime.push(await invoke("B40", () => native.select_prediction_model(values.station_request, values.release_view, values.selection_options, values.reader_version), JSON.stringify({ station_request: values.station_request, release_view: values.release_view, selection_options: values.selection_options, reader_version: values.reader_version })));
        runtime.push(await invoke("B41", () => native.evaluate_astronomy(values.selected_prediction_model, values.utc_instant), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, utc_instant: values.utc_instant })));
        runtime.push(await invoke("B42", () => native.evaluate_harmonic_height(values.selected_prediction_model, values.prediction_instants, values.requested_datum), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, prediction_instants: values.prediction_instants, requested_datum: values.requested_datum })));
        runtime.push(await invoke("B43", () => native.find_tide_events(values.selected_prediction_model, values.prediction_window), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, prediction_window: values.prediction_window })));
        runtime.push(await invoke("B44", () => native.evaluate_direct_current(values.selected_prediction_model, values.prediction_window, values.current_request, values.current_operation), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, prediction_window: values.prediction_window, current_request: values.current_request, current_operation: values.current_operation })));
        runtime.push(await invoke("B45", () => native.evaluate_tide_offset(values.own_offset, values.reference_path, values.prediction_window, values.tide_request, values.reader_version), JSON.stringify({ own_offset: values.own_offset, reference_path: values.reference_path, prediction_window: values.prediction_window, tide_request: values.tide_request, reader_version: values.reader_version })));
        runtime.push(await invoke("B46", () => native.fold_equal_tide_offset(values.own_offset, values.reference_model, values.prediction_instants, values.requested_datum), JSON.stringify({ own_offset: values.own_offset, reference_model: values.reference_model, prediction_instants: values.prediction_instants, requested_datum: values.requested_datum })));
        runtime.push(await invoke("B47", () => native.evaluate_current_offset(values.own_current_offsets, values.reference_path, values.prediction_window, values.current_request, values.reader_version), JSON.stringify({ own_current_offsets: values.own_current_offsets, reference_path: values.reference_path, prediction_window: values.prediction_window, current_request: values.current_request, reader_version: values.reader_version })));
        runtime.push(await invoke("B48", () => native.dispatch_auxiliary_result(values.auxiliary_kind, values.auxiliary_operation, values.source_values, values.result_context, values.local_time_profile, values.result_values, values.utc_result, values.selection_options, values.reader_version, values.auxiliary_member_id), JSON.stringify({ auxiliary_kind: values.auxiliary_kind, auxiliary_operation: values.auxiliary_operation, source_values: values.source_values, result_context: values.result_context, local_time_profile: values.local_time_profile, result_values: values.result_values, utc_result: values.utc_result, selection_options: values.selection_options, reader_version: values.reader_version, auxiliary_member_id: values.auxiliary_member_id })));
        runtime.push(await invoke("B08.raw", () => native.retain_raw_source_record(values.source_record, values.native_profile), JSON.stringify({ source_record: values.source_record, native_profile: values.native_profile })));
        runtime.push(await invoke("B08.origin", () => native.check_station_origin(values.station, values.release_origin), JSON.stringify({ station: values.station, release_origin: values.release_origin })));
        runtime.push(await invoke("B23.lock", () => native.manage_cache_lock(values.lock_request, values.lock_state, values.clock), JSON.stringify({ lock_request: values.lock_request, lock_state: values.lock_state, clock: values.clock })));
        runtime.push(await invoke("B23.http", () => native.request_http_resource(values.http_request, values.transport_options), JSON.stringify({ http_request: values.http_request, transport_options: values.transport_options })));
        runtime.push(await invoke("B35.stats", () => native.count_release_statistics(values.release_view), JSON.stringify({ release_view: values.release_view })));
        runtime.push(await invoke("B35.sets", () => native.order_constant_sets(values.station_sets, values.original_recommendation, values.commercial_only, values.include_no_constants), JSON.stringify({ station_sets: values.station_sets, original_recommendation: values.original_recommendation, commercial_only: values.commercial_only, include_no_constants: values.include_no_constants })));
        runtime.push(await invoke("B48.aux", () => native.read_auxiliary_model_value(values.auxiliary_operation, values.source_values, values.selection_options, values.reader_version, values.auxiliary_member_id), JSON.stringify({ auxiliary_operation: values.auxiliary_operation, source_values: values.source_values, selection_options: values.selection_options, reader_version: values.reader_version, auxiliary_member_id: values.auxiliary_member_id })));
        runtime.push(await invoke("B48.context", () => native.construct_prediction_result(values.result_values, values.result_context), JSON.stringify({ result_values: values.result_values, result_context: values.result_context })));
        runtime.push(await invoke("B48.local", () => native.convert_result_to_local_time(values.utc_result, values.local_time_profile), JSON.stringify({ utc_result: values.utc_result, local_time_profile: values.local_time_profile })));
        runtime.push(await invoke("B43.roots", () => native.find_unrounded_tide_events(values.selected_prediction_model, values.prediction_window), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, prediction_window: values.prediction_window })));
        runtime.push(await invoke("B44.roots", () => native.find_unrounded_current_events(currentModel, currentWindow, values.current_request), JSON.stringify({ selected_prediction_model: currentModel, prediction_window: currentWindow, current_request: values.current_request })));
        runtime.push(await invoke("B17.sidecar", () => native.acquire_checksum_sidecar(values.acquisition_descriptor, values.effective_options), JSON.stringify({ acquisition_descriptor: values.acquisition_descriptor, effective_options: values.effective_options })));
        call_actions.push({ ...await invoke("B08.raw", () => native.retain_raw_source_record(values.source_record, values.native_profile), JSON.stringify({ source_record: values.source_record, native_profile: values.native_profile })), id: "B08.S1.A1" });
        call_actions.push({ ...await invoke("B08.origin", () => native.check_station_origin(values.station, values.release_origin), JSON.stringify({ station: values.station, release_origin: values.release_origin })), id: "B08.S1.A2" });
        call_actions.push({ ...await invoke("B01", () => native.validate_operation_arguments(values.operation, values.arguments, values.member_contract), JSON.stringify({ operation: values.operation, arguments: values.arguments, member_contract: values.member_contract })), id: "B09.S1.A3" });
        call_actions.push({ ...await invoke("B02", () => native.resolve_effective_options(values.explicit_options, values.environment, values.platform_defaults), JSON.stringify({ explicit_options: values.explicit_options, environment: values.environment, platform_defaults: values.platform_defaults })), id: "B09.S1.A4" });
        call_actions.push({ ...await invoke("B10", () => native.resolve_release_request(values.release_request, values.effective_options, values.cache_state, values.clock, values.reader_version), JSON.stringify({ release_request: values.release_request, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock, reader_version: values.reader_version })), id: "B09.S1.A5" });
        call_actions.push({ ...await invoke("B16", () => native.bind_checksum_manifest(values.checksum_bytes, values.pointer_digests, values.required_files), JSON.stringify({ checksum_bytes: values.checksum_bytes, pointer_digests: values.pointer_digests, required_files: values.required_files })), id: "B09.S2.A4" });
        call_actions.push({ ...await invoke("B05", () => native.decode_release_document(values.source_bytes, values.reader_version, values.document_kind), JSON.stringify({ source_bytes: values.source_bytes, reader_version: values.reader_version, document_kind: values.document_kind })), id: "B09.S2.A9" });
        call_actions.push({ ...await invoke("B06", () => native.validate_release_links(values.parsed_document, values.required_links), JSON.stringify({ parsed_document: values.parsed_document, required_links: values.required_links })), id: "B09.S2.A11" });
        call_actions.push({ ...await invoke("B19", () => native.select_cached_release(values.release_candidates, values.effective_options, values.cache_state, values.clock), JSON.stringify({ release_candidates: values.release_candidates, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock })), id: "B10.S1.A2" });
        call_actions.push({ ...await invoke("B17", () => native.acquire_release_files(values.acquisition_descriptor, values.effective_options, values.load_mode, values.cache_state, values.clock, values.reader_version), JSON.stringify({ load_mode: values.load_mode, cache_state: values.cache_state, acquisition_descriptor: values.acquisition_descriptor, effective_options: values.effective_options, clock: values.clock, reader_version: values.reader_version })), id: "B10.S1.A5" });
        call_actions.push({ ...await invoke("B19", () => native.select_cached_release(values.release_candidates, values.effective_options, values.cache_state, values.clock), JSON.stringify({ release_candidates: values.release_candidates, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock })), id: "B10.S2.A1" });
        call_actions.push({ ...await invoke("B11", () => native.exchange_release_metadata(values.metadata_request, values.trusted_cache, values.transport_options, values.cache_state, values.clock, values.reader_version), JSON.stringify({ metadata_request: values.metadata_request, trusted_cache: values.trusted_cache, transport_options: values.transport_options, cache_state: values.cache_state, clock: values.clock, reader_version: values.reader_version })), id: "B10.S3.A4" });
        call_actions.push({ ...await invoke("B17", () => native.acquire_release_files(values.acquisition_descriptor, values.effective_options, values.load_mode, values.cache_state, values.clock, values.reader_version), JSON.stringify({ load_mode: values.load_mode, cache_state: values.cache_state, acquisition_descriptor: values.acquisition_descriptor, effective_options: values.effective_options, clock: values.clock, reader_version: values.reader_version })), id: "B10.S3.A6" });
        call_actions.push({ ...await invoke("B19", () => native.select_cached_release(values.release_candidates, values.effective_options, values.cache_state, values.clock), JSON.stringify({ release_candidates: values.release_candidates, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock })), id: "B10.S4.A1" });
        call_actions.push({ ...await invoke("B23.http", () => native.request_http_resource(values.http_request, values.transport_options), JSON.stringify({ http_request: values.http_request, transport_options: values.transport_options })), id: "B11.S2.A2" });
        call_actions.push({ ...await invoke("B05", () => native.decode_release_document(values.source_bytes, values.reader_version, values.document_kind), JSON.stringify({ source_bytes: values.source_bytes, reader_version: values.reader_version, document_kind: values.document_kind })), id: "B11.S3.A5" });
        call_actions.push({ ...await invoke("B23.lock", () => native.manage_cache_lock(values.lock_request, values.lock_state, values.clock), JSON.stringify({ lock_request: values.lock_request, lock_state: values.lock_state, clock: values.clock })), id: "B11.S5.A2" });
        call_actions.push({ ...await invoke("B28", () => native.encode_cache_json(values.cache_document), JSON.stringify({ cache_document: values.cache_document })), id: "B11.S5.A4" });
        call_actions.push({ ...await invoke("B15", () => native.enforce_resource_lifetime(values.resource_state, values.lifetime_action), JSON.stringify({ resource_state: values.resource_state, lifetime_action: values.lifetime_action })), id: "B12.S1.A3" });
        call_actions.push({ ...await invoke("B11", () => native.exchange_release_metadata(values.metadata_request, values.trusted_cache, values.transport_options, values.cache_state, values.clock, values.reader_version), JSON.stringify({ metadata_request: values.metadata_request, trusted_cache: values.trusted_cache, transport_options: values.transport_options, cache_state: values.cache_state, clock: values.clock, reader_version: values.reader_version })), id: "B12.S1.A7" });
        call_actions.push({ ...await invoke("B10", () => native.resolve_release_request(values.release_request, values.effective_options, values.cache_state, values.clock, values.reader_version), JSON.stringify({ release_request: values.release_request, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock, reader_version: values.reader_version })), id: "B12.S2.A2" });
        call_actions.push({ ...await invoke("B12", () => native.update_client_release(values.client_state, values.update_request, values.clock, values.reader_version), JSON.stringify({ client_state: values.client_state, update_request: values.update_request, clock: values.clock, reader_version: values.reader_version })), id: "B13.S3.A2" });
        call_actions.push({ ...await invoke("B15", () => native.enforce_resource_lifetime(values.resource_state, values.lifetime_action), JSON.stringify({ resource_state: values.resource_state, lifetime_action: values.lifetime_action })), id: "B14.S2.A2" });
        call_actions.push({ ...await invoke("B23.lock", () => native.manage_cache_lock(values.lock_request, values.lock_state, values.clock), JSON.stringify({ lock_request: values.lock_request, lock_state: values.lock_state, clock: values.clock })), id: "B17.S1.A2" });
        call_actions.push({ ...await invoke("B19", () => native.select_cached_release(values.release_candidates, values.effective_options, values.cache_state, values.clock), JSON.stringify({ release_candidates: values.release_candidates, effective_options: values.effective_options, cache_state: values.cache_state, clock: values.clock })), id: "B17.S1.A3" });
        call_actions.push({ ...await invoke("B17.sidecar", () => native.acquire_checksum_sidecar(values.acquisition_descriptor, values.effective_options), JSON.stringify({ acquisition_descriptor: values.acquisition_descriptor, effective_options: values.effective_options })), id: "B17.S2.A1" });
        call_actions.push({ ...await invoke("B16", () => native.bind_checksum_manifest(values.checksum_bytes, values.pointer_digests, values.required_files), JSON.stringify({ checksum_bytes: values.checksum_bytes, pointer_digests: values.pointer_digests, required_files: values.required_files })), id: "B17.S2.A3" });
        call_actions.push({ ...await invoke("B23.http", () => native.request_http_resource(values.http_request, values.transport_options), JSON.stringify({ http_request: values.http_request, transport_options: values.transport_options })), id: "B17.S2.A6" });
        call_actions.push({ ...await invoke("B18", () => native.merge_cache_receipt(values.locked_cache_state, values.verified_file_rows, values.release_metadata), JSON.stringify({ locked_cache_state: values.locked_cache_state, verified_file_rows: values.verified_file_rows, release_metadata: values.release_metadata })), id: "B17.S4.A2" });
        call_actions.push({ ...await invoke("B25", () => native.authenticate_station_index(values.source_files, values.supplied_index, values.index_presence, values.reader_version), JSON.stringify({ source_files: values.source_files, supplied_index: values.supplied_index, index_presence: values.index_presence, reader_version: values.reader_version })), id: "B17.S5.A4" });
        call_actions.push({ ...await invoke("B28", () => native.encode_cache_json(values.cache_document), JSON.stringify({ cache_document: values.cache_document })), id: "B18.S4.A2" });
        call_actions.push({ ...await invoke("B23.lock", () => native.manage_cache_lock(values.lock_request, values.lock_state, values.clock), JSON.stringify({ lock_request: values.lock_request, lock_state: values.lock_state, clock: values.clock })), id: "B19.S3.A2" });
        call_actions.push({ ...await invoke("B16", () => native.bind_checksum_manifest(values.checksum_bytes, values.pointer_digests, values.required_files), JSON.stringify({ checksum_bytes: values.checksum_bytes, pointer_digests: values.pointer_digests, required_files: values.required_files })), id: "B20.S2.A2" });
        call_actions.push({ ...await invoke("B16", () => native.bind_checksum_manifest(values.checksum_bytes, values.pointer_digests, values.required_files), JSON.stringify({ checksum_bytes: values.checksum_bytes, pointer_digests: values.pointer_digests, required_files: values.required_files })), id: "B21.S2.A1" });
        call_actions.push({ ...await invoke("B23.lock", () => native.manage_cache_lock(values.lock_request, values.lock_state, values.clock), JSON.stringify({ lock_request: values.lock_request, lock_state: values.lock_state, clock: values.clock })), id: "B22.S4.A2" });
        call_actions.push({ ...await invoke("B23.lock", () => native.manage_cache_lock(values.lock_request, values.lock_state, values.clock), JSON.stringify({ lock_request: values.lock_request, lock_state: values.lock_state, clock: values.clock })), id: "B23.S1.A5" });
        call_actions.push({ ...await invoke("B23.http", () => native.request_http_resource(values.http_request, values.transport_options), JSON.stringify({ http_request: values.http_request, transport_options: values.transport_options })), id: "B23.S1.A7" });
        call_actions.push({ ...await invoke("B24", () => native.project_station_index(values.station_source_row, values.source_byte_span, values.projection_contract), JSON.stringify({ station_source_row: values.station_source_row, source_byte_span: values.source_byte_span, projection_contract: values.projection_contract })), id: "B25.S4.A4" });
        call_actions.push({ ...await invoke("B28", () => native.encode_cache_json(values.cache_document), JSON.stringify({ cache_document: values.cache_document })), id: "B25.S4.A6" });
        call_actions.push({ ...await invoke("B15", () => native.enforce_resource_lifetime(values.resource_state, values.lifetime_action), JSON.stringify({ resource_state: values.resource_state, lifetime_action: values.lifetime_action })), id: "B27.S1.A1" });
        call_actions.push({ ...await invoke("B05", () => native.decode_release_document(values.source_bytes, values.reader_version, values.document_kind), JSON.stringify({ source_bytes: values.source_bytes, reader_version: values.reader_version, document_kind: values.document_kind })), id: "B27.S4.A3" });
        call_actions.push({ ...await invoke("B26", () => native.compare_station_source(values.index_entry, values.station_source_row, values.index_presence), JSON.stringify({ index_entry: values.index_entry, station_source_row: values.station_source_row, index_presence: values.index_presence })), id: "B27.S4.A7" });
        call_actions.push({ ...await invoke("B27", () => native.read_station_lazily(values.stream_reader, values.station_id, values.release_origin, values.reader_version), JSON.stringify({ stream_reader: values.stream_reader, station_id: values.station_id, release_origin: values.release_origin, reader_version: values.reader_version })), id: "B29.S4.A4" });
        call_actions.push({ ...await invoke("B07", () => native.materialize_typed_model(values.raw_fields, values.field_contract, values.origin, values.model_type), JSON.stringify({ raw_fields: values.raw_fields, field_contract: values.field_contract, origin: values.origin, model_type: values.model_type })), id: "B29.S4.A8" });
        call_actions.push({ ...await invoke("B15", () => native.enforce_resource_lifetime(values.resource_state, values.lifetime_action), JSON.stringify({ resource_state: values.resource_state, lifetime_action: values.lifetime_action })), id: "B34.S1.A1" });
        call_actions.push({ ...await invoke("B30", () => native.select_effective_recommendation(values.station_sets, values.original_recommendation, values.commercial_only), JSON.stringify({ station_sets: values.station_sets, original_recommendation: values.original_recommendation, commercial_only: values.commercial_only })), id: "B34.S2.A4" });
        call_actions.push({ ...await invoke("B33", () => native.resolve_reference_path(values.station_source_row, values.path_request, values.release_view), JSON.stringify({ station_source_row: values.station_source_row, path_request: values.path_request, release_view: values.release_view })), id: "B34.S2.A6" });
        call_actions.push({ ...await invoke("B31", () => native.admit_quality_path(values.candidate_path, values.include_flagged, values.include_fallback), JSON.stringify({ candidate_path: values.candidate_path, include_flagged: values.include_flagged, include_fallback: values.include_fallback })), id: "B34.S3.A3" });
        call_actions.push({ ...await invoke("B32", () => native.admit_commercial_path(values.candidate_path, values.commercial_only, values.commercial_basis), JSON.stringify({ candidate_path: values.candidate_path, commercial_only: values.commercial_only, commercial_basis: values.commercial_basis })), id: "B34.S3.A4" });
        call_actions.push({ ...await invoke("B36", () => native.admit_historical_offset(values.own_offset, values.reference_path, values.historical_policy, values.selection_kind, values.reader_version), JSON.stringify({ own_offset: values.own_offset, reference_path: values.reference_path, historical_policy: values.historical_policy, selection_kind: values.selection_kind, reader_version: values.reader_version })), id: "B34.S3.A8" });
        call_actions.push({ ...await invoke("B35.stats", () => native.count_release_statistics(values.release_view), JSON.stringify({ release_view: values.release_view })), id: "B35.S1.A1" });
        call_actions.push({ ...await invoke("B35.sets", () => native.order_constant_sets(values.station_sets, values.original_recommendation, values.commercial_only, values.include_no_constants), JSON.stringify({ station_sets: values.station_sets, original_recommendation: values.original_recommendation, commercial_only: values.commercial_only, include_no_constants: values.include_no_constants })), id: "B35.S1.A2" });
        call_actions.push({ ...await invoke("B40", () => native.select_prediction_model(values.station_request, values.release_view, values.selection_options, values.reader_version), JSON.stringify({ release_view: values.release_view, selection_options: values.selection_options, station_request: values.station_request, reader_version: values.reader_version })), id: "B36.S7.A2" });
        call_actions.push({ ...await invoke("B08.origin", () => native.check_station_origin(values.station, values.release_origin), JSON.stringify({ station: values.station, release_origin: values.release_origin })), id: "B37.S1.A2" });
        call_actions.push({ ...await invoke("B30", () => native.select_effective_recommendation(values.station_sets, values.original_recommendation, values.commercial_only), JSON.stringify({ station_sets: values.station_sets, original_recommendation: values.original_recommendation, commercial_only: values.commercial_only })), id: "B37.S2.A3" });
        call_actions.push({ ...await invoke("B33", () => native.resolve_reference_path(values.station_source_row, values.path_request, values.release_view), JSON.stringify({ station_source_row: values.station_source_row, path_request: values.path_request, release_view: values.release_view })), id: "B37.S2.A5" });
        call_actions.push({ ...await invoke("B08.origin", () => native.check_station_origin(values.station, values.release_origin), JSON.stringify({ station: values.station, release_origin: values.release_origin })), id: "B40.S1.A2" });
        call_actions.push({ ...await invoke("B29", () => native.lookup_station_identity(values.release_view, values.identity_query, values.reader_version), JSON.stringify({ release_view: values.release_view, identity_query: values.identity_query, reader_version: values.reader_version })), id: "B40.S1.A3" });
        call_actions.push({ ...await invoke("B30", () => native.select_effective_recommendation(values.station_sets, values.original_recommendation, values.commercial_only), JSON.stringify({ station_sets: values.station_sets, original_recommendation: values.original_recommendation, commercial_only: values.commercial_only })), id: "B40.S2.A4" });
        call_actions.push({ ...await invoke("B41", () => native.evaluate_astronomy(values.selected_prediction_model, values.utc_instant), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, utc_instant: values.utc_instant })), id: "B42.S1.A2" });
        call_actions.push({ ...await invoke("B43.roots", () => native.find_unrounded_tide_events(values.selected_prediction_model, values.prediction_window), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, prediction_window: values.prediction_window })), id: "B43.S1.A1" });
        call_actions.push({ ...await invoke("B44.roots", () => native.find_unrounded_current_events(currentModel, currentWindow, values.current_request), JSON.stringify({ selected_prediction_model: currentModel, prediction_window: currentWindow, current_request: values.current_request })), id: "B44.S1.A1" });
        call_actions.push({ ...await invoke("B36", () => native.admit_historical_offset(values.own_offset, values.reference_path, values.historical_policy, values.selection_kind, values.reader_version), JSON.stringify({ own_offset: values.own_offset, reference_path: values.reference_path, historical_policy: values.historical_policy, selection_kind: values.selection_kind, reader_version: values.reader_version })), id: "B45.S2.A3" });
        call_actions.push({ ...await invoke("B40", () => native.select_prediction_model(values.station_request, values.release_view, values.selection_options, values.reader_version), JSON.stringify({ release_view: values.release_view, selection_options: values.selection_options, station_request: values.station_request, reader_version: values.reader_version })), id: "B45.S3.A2" });
        call_actions.push({ ...await invoke("B43.roots", () => native.find_unrounded_tide_events(values.selected_prediction_model, values.prediction_window), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, prediction_window: values.prediction_window })), id: "B45.S6.A2" });
        call_actions.push({ ...await invoke("B46", () => native.fold_equal_tide_offset(values.own_offset, values.reference_model, values.prediction_instants, values.requested_datum), JSON.stringify({ own_offset: values.own_offset, reference_model: values.reference_model, prediction_instants: values.prediction_instants, requested_datum: values.requested_datum })), id: "B45.S7.A3" });
        call_actions.push({ ...await invoke("B42", () => native.evaluate_harmonic_height(values.selected_prediction_model, values.prediction_instants, values.requested_datum), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, prediction_instants: values.prediction_instants, requested_datum: values.requested_datum })), id: "B46.S3.A2" });
        call_actions.push({ ...await invoke("B40", () => native.select_prediction_model(values.station_request, values.release_view, values.selection_options, values.reader_version), JSON.stringify({ release_view: values.release_view, selection_options: values.selection_options, station_request: values.station_request, reader_version: values.reader_version })), id: "B47.S2.A2" });
        call_actions.push({ ...await invoke("B44.roots", () => native.find_unrounded_current_events(currentModel, currentWindow, values.current_request), JSON.stringify({ selected_prediction_model: currentModel, prediction_window: currentWindow, current_request: values.current_request })), id: "B47.S4.A3" });
        call_actions.push({ ...await invoke("B48.aux", () => native.read_auxiliary_model_value(values.auxiliary_operation, values.source_values, values.selection_options, values.reader_version, values.auxiliary_member_id), JSON.stringify({ source_values: values.source_values, selection_options: values.selection_options, auxiliary_operation: values.auxiliary_operation, reader_version: values.reader_version, auxiliary_member_id: values.auxiliary_member_id })), id: "B48.S1.A1" });
        call_actions.push({ ...await invoke("B48.context", () => native.construct_prediction_result(values.result_values, values.result_context), JSON.stringify({ result_values: values.result_values, result_context: values.result_context })), id: "B48.S1.A2" });
        call_actions.push({ ...await invoke("B48.local", () => native.convert_result_to_local_time(values.utc_result, values.local_time_profile), JSON.stringify({ utc_result: values.utc_result, local_time_profile: values.local_time_profile })), id: "B48.S1.A3" });
        call_actions.push({ ...await invoke("B30", () => native.select_effective_recommendation(values.station_sets, values.original_recommendation, values.commercial_only), JSON.stringify({ station_sets: values.station_sets, original_recommendation: values.original_recommendation, commercial_only: values.commercial_only })), id: "B35.sets.S1.A1" });
        call_actions.push({ ...await invoke("B40", () => native.select_prediction_model(values.station_request, values.release_view, values.selection_options, values.reader_version), JSON.stringify({ release_view: values.release_view, selection_options: values.selection_options, station_request: values.station_request, reader_version: values.reader_version })), id: "B48.aux.S2.A1" });
        call_actions.push({ ...await invoke("B41", () => native.evaluate_astronomy(values.selected_prediction_model, values.utc_instant), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, utc_instant: values.utc_instant })), id: "B48.aux.S2.A2" });
        call_actions.push({ ...await invoke("B41", () => native.evaluate_astronomy(values.selected_prediction_model, values.utc_instant), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, utc_instant: values.utc_instant })), id: "B43.roots.S1.A2" });
        call_actions.push({ ...await invoke("B41", () => native.evaluate_astronomy(values.selected_prediction_model, values.utc_instant), JSON.stringify({ selected_prediction_model: values.selected_prediction_model, utc_instant: values.utc_instant })), id: "B44.roots.S2.A2" });
        call_actions.push({ ...await invoke("B23.http", () => native.request_http_resource(values.http_request, values.transport_options), JSON.stringify({ http_request: values.http_request, transport_options: values.transport_options })), id: "B17.sidecar.S1.A3" });
        const removedTombstone = release.tombstone('OTC-T-0005');
        if (!removedTombstone) throw new Error('Authentic native removed Tombstone is required');
        const removedReason = typeof removedTombstone.raw['removed_reason'] === 'string' ? removedTombstone.raw['removed_reason'] : null;
        const bindingVariants: readonly C.NativeBindingInputs[] = [
            { native_profile: profile, canonical_result: { presence: 'successful_no_value', member_id: 'Client.close' } },
            { native_profile: profile, canonical_result: { presence: 'present_value', binding: { member_id: 'Release.station', value: null } } },
            { native_profile: profile, canonical_error: { code: 'io', structured_fields: {}, cause: new Error('original cause') } },
            { native_profile: profile, native_exception: new Error('native exception'), member_id: 'Release.station' },
            { native_profile: profile, canonical_error: { code: 'network', structured_fields: { message: 'transport fixture failed', url: 'https://native.invalid/release', status: 503 }, cause: new Error('original native cause') } },
            { native_profile: profile, canonical_error: { code: 'checksum_mismatch', structured_fields: { message: 'injected digest disagreement', file: 'OTC_20991231.2.json', expected: 'a'.repeat(64), actual: 'b'.repeat(64) }, cause: new Error('original native cause') } },
            { native_profile: profile, canonical_error: { code: 'cache', structured_fields: { message: 'injected prune failure', removed: ['20991231.2', '20991231'] }, cause: new Error('original native cause') } },
            { native_profile: profile, canonical_error: { code: 'station_not_found', structured_fields: {}, cause: null }, native_constructor_context: { code: 'station_not_found', stationId: 'OTC-native-missing-context' } },
            { native_profile: profile, canonical_error: { code: 'station_removed', structured_fields: {}, cause: null }, native_constructor_context: { code: 'station_removed', stationId: removedTombstone.station_id, tombstone: removedTombstone, reason: removedReason } },
            { native_profile: profile, canonical_error: { code: 'file_exists', structured_fields: {}, cause: null }, native_constructor_context: { code: 'file_exists', path: '/native/typed-constructor-control' } },
            { native_profile: profile, canonical_error: { code: 'release_not_found', structured_fields: { message: '' }, cause: null }, native_cause_option: { presence: 'present', value: null } },
        ];
        const b04_presence_controls = await Promise.all(bindingVariants.map(async (input, index) => ({ ...await invoke('B04', () => native.translate_native_binding(input), JSON.stringify(input)), id: `B04.presence.${index}` })));
        return { runtime, call_actions, b04_presence_controls, control: { station_id: station.station_id, raw_preserved: station.raw.station_id === station.station_id, public_route_unchanged: release.station(station.station_id) === station } };
    } finally {
        predictionRelease._close();
        release._close();
    }
}
