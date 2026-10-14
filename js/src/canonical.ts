import type * as C from './canonical-types.js';
import { deepFreeze, isObject, arr, str, num, type JsonObject } from './json.js';
import { encodeCacheJson } from './cache-json.js';
import { Station, ConstantSet, indexDoc, constituentOf, timeBaseOf, buildOf, validationOf, fallbackOf, qcFlagOf, sourceRecordOf, checkFilters, validateSearchOptions, validateNearOptions, validateNearestOptions, validateConstantSetsOptions,
    recordSpanOf, datumOf, droppedConstituentOf, provenanceOf, conventionOf, licenceOf, tombstoneOf, subordinateOffsetsOf, historicalVintageOf, historicalProvenanceOf, nearbyOf, statsOf, releaseFromPrepared, predictionOptions, validateAllSets, validateAttributionList } from './release.js';
import * as X from './errors.js';
import { AstroTable, instant, utc, validateUtcYear } from './predict/astro.js';
import { validateLocalTimeType } from './predict/local.js';
import { Sum, unroundedEvents } from './predict/harmonic.js';
import { window as nativeWindow, contextFor, datumTerm, unroundedCurrentEventsFor, bin, currentContext, predictionSeconds, validateOffsetArguments } from './predict/engine.js';
import { validateOpenOptions, resolveOpenNativeOptions, validateDownloadOptions, validatePruneOptions, toInfo, updateResultOf, clientArgumentReceiver, clientFromPrepared } from './client.js';
import { fileInfoOf } from './core.js';
import type { OpenOptions } from './types.js';
import * as R from './predict/results.js';

/** A private seam has been constructed, but its wider algorithm remains on the primary body. */
export class CanonicalUnimplementedError extends Error {
    constructor(readonly behavior: string) {
        super(`Private canonical seam ${behavior} is unimplemented`);
        this.name = 'CanonicalUnimplementedError';
    }
}

export function validate_operation_arguments(operation: C.operation, operation_arguments: C.arguments, member_contract: C.member_contract): C.validated_arguments {
    if (operation_arguments.member_id !== member_contract.member_id) throw new X.InvalidArgumentError('member contract does not match the requested operation');
    if (operation_arguments.member_id === 'Client.open') {
        validateOpenOptions(nativeOpenOptions(operation_arguments.arguments));
        return operation_arguments;
    }
    const receiver = member_contract.native_receiver;
    let capability: ReturnType<typeof clientArgumentReceiver> | undefined;
    if (operation_arguments.member_id === 'Client.download' || operation_arguments.member_id === 'Client.prune') {
        if (receiver?.kind !== 'client') throw new CanonicalUnimplementedError('B01 requires its native Client receiver');
        capability = clientArgumentReceiver(receiver.owner);
    }
    if (['Release.stations', 'Release.iter_stations', 'Release.search', 'Release.near', 'Release.nearest', 'Release.heights', 'Release.heights_at', 'Release.extremes', 'Release.currents', 'Release.current_events', 'Release.datums', 'Release.ranges', 'Release.convention', 'Release.licence', 'Release.station', 'Release.require_station', 'Release.tombstone', 'Release.station_by_alias', 'Release.astro_table', 'Release.reference_station', 'Release.subordinates_of', 'Release.attribution'].includes(operation_arguments.member_id)) {
        if (receiver?.kind !== 'release') throw new CanonicalUnimplementedError('B01 requires its native Release receiver');
        void receiver.owner._header;
    }
    if ('native_guard' in member_contract && member_contract.native_guard === 'no_arguments') {
        const member = member_contract.member_id;
        const clientMetadata = ['Client.close', 'Client.release', 'Client.loaded_from', 'Client.last_error', 'Client.newer_format_major'];
        const releaseMetadata = ['Release.datestamp', 'Release.created', 'Release.format_version', 'Release.concept_doi', 'Release.zenodo_version_doi', 'Release.source_versions', 'Release.build_commit', 'Release.changelog_url', 'Release.files', 'Release.citation'];
        if (member.startsWith('Client.') && !clientMetadata.includes(member)) {
            if (receiver?.kind !== 'client') throw new CanonicalUnimplementedError('B01 requires its native Client receiver');
            clientArgumentReceiver(receiver.owner);
        }
        if (member.startsWith('Release.') && !releaseMetadata.includes(member)) {
            if (receiver?.kind !== 'release') throw new CanonicalUnimplementedError('B01 requires its native Release receiver');
            void receiver.owner._header;
        }
        if (Object.keys(operation_arguments.arguments).length !== 0) throw new X.InvalidArgumentError(`${member_contract.member_id} takes no arguments`);
        return operation_arguments;
    }
    if (operation_arguments.member_id === 'Client.close') return operation_arguments;
    switch (operation_arguments.member_id) {
        case 'Client.download':
            if (capability && !capability.node) throw new X.UnsupportedError('download needs a file system (Node)');
            validateDownloadOptions(operation_arguments.arguments); return operation_arguments;
        case 'Client.prune':
            validatePruneOptions(operation_arguments.arguments);
            if (capability && (!capability.node || !capability.store)) throw new X.UnsupportedError('prune needs a file system (Node)');
            return operation_arguments;
        case 'Station.constant_sets': validateConstantSetsOptions({ includeNoConstants: operation_arguments.arguments.include_no_constants }); return operation_arguments;
        case 'Station.constant_set': case 'ConstantSet.constituent': return operation_arguments;
        case 'Release.convention': case 'Release.licence': case 'Release.station': case 'Release.require_station': case 'Release.tombstone': case 'Release.station_by_alias': case 'Release.astro_table': return operation_arguments;
        case 'Release.reference_station': case 'Release.subordinates_of':
            consumeOwnerPrerequisite(operation_arguments, member_contract);
            return operation_arguments;
        case 'Release.attribution':
            validateAttributionList(operation_arguments.arguments.stations);
            consumeOwnerPrerequisite(operation_arguments, member_contract);
            return operation_arguments;
        case 'Release.stations': case 'Release.iter_stations': checkFilters(nativeFilters(operation_arguments.arguments)); return operation_arguments;
        case 'Release.search': validateSearchOptions({ ...nativeFilters(operation_arguments.arguments), ...operation_arguments.arguments }); return operation_arguments;
        case 'Release.near': validateNearOptions({ ...nativeFilters(operation_arguments.arguments), ...operation_arguments.arguments, radiusKm: operation_arguments.arguments.radius_km }); return operation_arguments;
        case 'Release.nearest': validateNearestOptions({ ...nativeFilters(operation_arguments.arguments), ...operation_arguments.arguments, maxKm: operation_arguments.arguments.max_km }); return operation_arguments;
        case 'Release.heights': case 'Release.extremes': {
            const args = operation_arguments.arguments;
            nativeWindow(args.start, args.stop, operation_arguments.member_id === 'Release.heights' ? operation_arguments.arguments.step_s === undefined ? 600 : operation_arguments.arguments.step_s : undefined);
            consumePredictionPrerequisite(operation_arguments, member_contract);
            predictionOptions(args.set_id, args.datum);
            validateOffsetArguments(args.set_id, args.offset_id);
            return operation_arguments;
        }
        case 'Release.currents': case 'Release.current_events': {
            const args = operation_arguments.arguments;
            nativeWindow(args.start, args.stop, operation_arguments.member_id === 'Release.currents' ? operation_arguments.arguments.step_s === undefined ? 600 : operation_arguments.arguments.step_s : undefined);
            consumePredictionPrerequisite(operation_arguments, member_contract);
            predictionOptions(args.set_id, null, args.bin_number);
            return operation_arguments;
        }
        case 'Release.heights_at':
            predictionSeconds(operation_arguments.arguments.times);
            consumePredictionPrerequisite(operation_arguments, member_contract);
            predictionOptions(operation_arguments.arguments.set_id, operation_arguments.arguments.datum);
            validateOffsetArguments(operation_arguments.arguments.set_id, operation_arguments.arguments.offset_id);
            return operation_arguments;
        case 'Release.datums': case 'Release.ranges':
            consumePredictionPrerequisite(operation_arguments, member_contract);
            predictionOptions(operation_arguments.arguments.set_id);
            validateAllSets(operation_arguments.member_id === 'Release.datums' ? operation_arguments.arguments.all_sets : undefined);
            return operation_arguments;
        case 'AstroTable.equilibrium_argument': case 'AstroTable.node_factor':
            instant(operation_arguments.arguments.at);
            consumeAstronomyPrerequisite(operation_arguments, member_contract);
            return operation_arguments;
        case 'AstroTable.equilibrium_for_year': case 'AstroTable.node_factor_for_year':
            consumeAstronomyPrerequisite(operation_arguments, member_contract);
            validateUtcYear(operation_arguments.arguments.year);
            return operation_arguments;
        case 'HeightSeries.to_local': case 'ExtremeList.to_local': case 'CurrentSeries.to_local': case 'CurrentEventList.to_local':
            if (receiver?.kind !== 'result') throw new CanonicalUnimplementedError('B01 requires its native result receiver');
            validateLocalTimeType(operation_arguments.arguments.tz === undefined ? 'station' : operation_arguments.arguments.tz);
            return operation_arguments;
    }
    throw new CanonicalUnimplementedError(`B01 native validator ${operation}`);
}

function consumeOwnerPrerequisite(request: C.arguments, contract: C.member_contract): void {
    const prepared = contract.native_owner_prerequisite, receiver = contract.native_receiver;
    if (!prepared || receiver?.kind !== 'release' || prepared.receiver !== receiver.owner || prepared.request !== request) throw new CanonicalUnimplementedError('B01 requires its authentic ordered native ownership prerequisites');
    if (prepared.error) throw prepared.error;
    for (const outcome of prepared.outcomes) {
        if (outcome.error) throw outcome.error;
        if (!outcome.entry) throw new CanonicalUnimplementedError('B01 requires its resolved native ownership entry');
    }
}

function consumePredictionPrerequisite(request: C.arguments, contract: C.member_contract): void {
    const prepared = contract.native_prediction_prerequisite, receiver = contract.native_receiver;
    if (!prepared || receiver?.kind !== 'release' || prepared.receiver !== receiver.owner || prepared.request !== request) throw new CanonicalUnimplementedError('B01 requires its authentic native station prerequisite');
    if (prepared.error) throw prepared.error;
    if (!prepared.station) throw new CanonicalUnimplementedError('B01 requires its resolved native station');
}

function consumeAstronomyPrerequisite(request: C.arguments, contract: C.member_contract): void {
    const prepared = contract.native_astronomy_prerequisite, receiver = contract.native_receiver;
    if (!prepared || receiver?.kind !== 'astro_table' || prepared.receiver !== receiver.owner || prepared.request !== request) throw new CanonicalUnimplementedError('B01 requires its authentic native row prerequisite');
    if (prepared.error) throw prepared.error;
    if (!prepared.row) throw new CanonicalUnimplementedError('B01 requires its resolved native row');
}

function nativeFilters(filters: C.CanonicalStationFilters) {
    return { country: filters.country, type: filters.type, kind: filters.kind, source: filters.source, sourceType: filters.source_type,
        includeFlagged: filters.include_flagged, includeFallback: filters.include_fallback };
}

export function resolve_effective_options(explicit_options: C.explicit_options, environment: C.environment, platform_defaults: C.platform_defaults): C.effective_options {
    const options = nativeOpenOptions(explicit_options), validated = validateOpenOptions(options);
    const native = platform_defaults.native_context;
    if (!native) throw new CanonicalUnimplementedError('B02 requires the native platform defaults owner');
    const settings = resolveOpenNativeOptions(options, validated, { name: native.platform.name, env: name => environment[name] ?? native.platform.env(name) }, native.node);
    return { ...explicit_options, release: validated.release, mode: validated.mode, on_network_error: validated.onNetworkError,
        timeout: validated.timeout, auto_update: validated.autoUpdate, update_interval: validated.interval,
        verify_on_open: validated.verifyOnOpen, commercial_only: validated.commercialOnly === true,
        commercial_basis: validated.commercialBasis, historical_offsets_policy: validated.historicalOffsetsPolicy,
        offline: settings.offline, base_url: settings.baseUrl, proxy: settings.proxy, ca_file: settings.caFile, cache_dir: settings.cacheRoot ?? settings.cacheDir };
}

export function select_canonical_error(operation: C.operation, ordered_failures: C.ordered_failures, cause: C.cause): C.canonical_error {
    const selected = ordered_failures[0];
    if (!selected) throw new CanonicalUnimplementedError('B03 requires an applicable ordered failure');
    return selected.cause === null && cause !== null ? Object.freeze({ ...selected, cause }) : selected;
}

export function translate_native_binding(inputs: C.NativeBindingInputs): C.native_result {
    if ('native_exception' in inputs) throw inputs.native_exception;
    if (inputs.canonical_result) {
        if (inputs.canonical_result.presence === 'successful_no_value') return { member_id: 'Client.close', value: undefined };
        return inputs.canonical_result.binding;
    }
    const failure = inputs.canonical_error;
    if (!failure) throw new CanonicalUnimplementedError('B04 requires the selected member channel');
    if (failure.native_error) throw failure.native_error;
    const fields = isObject(failure.structured_fields) ? failure.structured_fields : null;
    const message = str(fields, 'message') ?? failure.code;
    const context = inputs.native_constructor_context;
    if (failure.code === 'station_not_found' || failure.code === 'station_removed' || failure.code === 'file_exists') {
        if (!context || context.code !== failure.code || failure.cause !== null || inputs.native_cause_option?.presence === 'present') throw new CanonicalUnimplementedError('B04 requires its genuine native constructor context');
        switch (context.code) {
            case 'station_not_found': throw new X.StationNotFoundError(context.stationId);
            case 'station_removed': throw new X.StationRemovedError(context.stationId, context.tombstone, context.reason);
            case 'file_exists': throw new X.FileExistsError(context.path);
        }
    }
    const nativeCause = inputs.native_cause_option;
    if (nativeCause?.presence === 'present' && nativeCause.value !== null && !(nativeCause.value instanceof Error)) throw new CanonicalUnimplementedError('B04 requires its bounded native cause option');
    if (nativeCause?.presence === 'present' && nativeCause.value instanceof Error && nativeCause.value !== failure.cause) throw new CanonicalUnimplementedError('B04 requires its original logical cause identity');
    const cause = nativeCause ? nativeCause.presence === 'present' ? { cause: nativeCause.value } : {} : { cause: failure.cause ?? undefined };
    switch (failure.code) {
        case 'release_not_found': throw new X.ReleaseNotFoundError(message, cause);
        case 'offline_unavailable': throw new X.OfflineError(message, cause);
        case 'unsupported_format': throw new X.UnsupportedFormatError(message, cause);
        case 'reader_too_old': throw new X.ReaderTooOldError(message, cause);
        case 'invalid_release': throw new X.InvalidReleaseError(message, cause);
        case 'no_constants': throw new X.NoConstantsError(message, cause);
        case 'quantity_mismatch': throw new X.QuantityMismatchError(message, cause);
        case 'unsupported_convention': throw new X.UnsupportedConventionError(message, cause);
        case 'no_astro_table': throw new X.NoAstroTableError(message, cause);
        case 'bin_not_found': throw new X.BinNotFoundError(message, cause);
        case 'extremes_only': throw new X.ExtremesOnlyError(message, cause);
        case 'local_time_unavailable': throw new X.LocalTimeUnavailableError(message, cause);
        case 'historical_offsets_excluded': throw new X.HistoricalOffsetsExcludedError(message, cause);
        case 'pinned_release': throw new X.PinnedReleaseError(message);
        case 'unsupported': throw new X.UnsupportedError(message);
        case 'unsupported_constituent': throw new X.UnsupportedConstituentError(message, { constituent: nativeErrorString(fields, 'constituent'), ...cause });
        case 'datum_unavailable': throw new X.DatumUnavailableError(message, { missing: nativeErrorString(fields, 'missing'), ...cause });
        case 'unknown_time_zone': throw new X.UnknownTimeZoneError(message, { zone: nativeErrorString(fields, 'zone'), ...cause });
        case 'reference_unavailable': throw new X.ReferenceUnavailableError(message, { reference_station_id: nativeErrorString(fields, 'reference_station_id'), ...cause });
        case 'time_out_of_range': {
            const first_year = num(fields, 'first_year'), last_year = num(fields, 'last_year');
            if (first_year === null || last_year === null) throw new CanonicalUnimplementedError('B04 requires its native year-range fields');
            throw new X.TimeOutOfRangeError(message, { first_year, last_year, ...cause });
        }
    }
    if (failure.code === 'invalid_argument') throw new X.InvalidArgumentError(message);
    if (failure.code === 'io') throw new X.FileError(message, { path: str(fields, 'path') ?? '', ...cause });
    if (failure.code === 'network') throw new X.NetworkError(message, { url: str(fields, 'url'), status: num(fields, 'status'), ...cause });
    if (failure.code === 'checksum_mismatch') {
        const file = str(fields, 'file');
        if (file === null) throw new CanonicalUnimplementedError('B04 checksum error requires its native file field');
        throw new X.ChecksumError(message, { file, expected: str(fields, 'expected'), actual: str(fields, 'actual'), ...cause });
    }
    if (failure.code === 'cache') {
        const removed = fields?.['removed'];
        if (removed !== undefined && (!Array.isArray(removed) || removed.some(item => typeof item !== 'string'))) throw new CanonicalUnimplementedError('B04 cache error requires its native removed fields');
        throw new X.CacheError(message, { removed: arr(fields, 'removed').filter((item): item is string => typeof item === 'string'), ...cause });
    }
    throw new CanonicalUnimplementedError(`B04 native error mapping ${failure.code}`);
}

function nativeErrorString(fields: JsonObject | null, key: 'constituent' | 'missing' | 'zone' | 'reference_station_id'): string | null {
    const value = fields?.[key];
    if (value !== null && typeof value !== 'string') throw new CanonicalUnimplementedError(`B04 requires its native ${key} field`);
    return value;
}

export function decode_release_document(source_bytes: C.source_bytes, reader_version: C.reader_version, document_kind: C.document_kind): C.parsed_document {
    throw new CanonicalUnimplementedError("B05");
}

export function validate_release_links(parsed_document: C.parsed_document, required_links: C.required_links): C.validated_release_graph {
    throw new CanonicalUnimplementedError("B06");
}

export function materialize_typed_model(raw_fields: C.raw_fields, field_contract: C.field_contract, origin: C.origin, model_type: C.model_type): C.typed_model {
    if (field_contract.model_type !== model_type || field_contract.fields.some(field => !field.startsWith(`${model_type}.`))) throw new X.InvalidReleaseError('field contract names a different model');
    if (model_type === 'Client' && field_contract.native_prepared_client && field_contract.native_prepared_client.sourceOptions === raw_fields) return { model_type, model: clientFromPrepared(field_contract.native_prepared_client) };
    if (model_type === 'Release' && field_contract.native_prepared_release && field_contract.native_prepared_release.authenticHeader.raw === raw_fields) return { model_type, model: releaseFromPrepared(field_contract.native_prepared_release) };
    if (model_type === 'Station' && field_contract.native_owner) return { model_type: 'Station', model: new Station(raw_fields, field_contract.native_owner.entry, field_contract.native_owner.release) };
    if (model_type === 'Constituent') return { model_type, model: constituentOf(raw_fields) };
    if (model_type === 'TimeBase') return { model_type, model: timeBaseOf(raw_fields) };
    if (model_type === 'ProvenanceBuild') return { model_type, model: buildOf(raw_fields) };
    if (model_type === 'Validation') return { model_type, model: validationOf(raw_fields) };
    if (model_type === 'Fallback') {
        const model = fallbackOf(raw_fields);
        if (model) return { model_type, model };
    }
    if (model_type === 'QcFlag') return { model_type, model: qcFlagOf(raw_fields) };
    if (model_type === 'SourceRecord' && field_contract.native_release) return { model_type, model: sourceRecordOf(raw_fields, field_contract.native_release) };
    if (model_type === 'ConstantSet' && field_contract.native_constant_set) {
        const owner = field_contract.native_constant_set;
        return { model_type, model: new ConstantSet(raw_fields, owner.recommended, owner.convention, owner.licence, owner.validation) };
    }
    if (model_type === 'AstroTable') return { model_type, model: new AstroTable(raw_fields) };
    if (model_type === 'RecordSpan' && field_contract.native_record_span) return { model_type, model: recordSpanOf(raw_fields, field_contract.native_record_span.set_id) };
    if (model_type === 'Datum') return { model_type, model: datumOf(raw_fields) };
    if (model_type === 'DroppedConstituent') return { model_type, model: droppedConstituentOf(raw_fields) };
    if (model_type === 'Provenance') return { model_type, model: provenanceOf(raw_fields) };
    if (model_type === 'Convention') return { model_type, model: conventionOf(raw_fields) };
    if (model_type === 'Licence') return { model_type, model: licenceOf(raw_fields) };
    if (model_type === 'Tombstone' && field_contract.native_owner) return { model_type, model: tombstoneOf(raw_fields, field_contract.native_owner.entry) };
    if (model_type === 'SubordinateOffsets') return { model_type, model: subordinateOffsetsOf(raw_fields) };
    const historicalParent = field_contract.native_historical_parent;
    if (historicalParent && model_type === 'HistoricalOffsetVintage' && historicalParent['vintage'] === raw_fields) {
        const model = historicalVintageOf(historicalParent);
        if (model) return { model_type, model };
    }
    if (historicalParent && model_type === 'HistoricalOffsetProvenance' && historicalParent['provenance'] === raw_fields) {
        const model = historicalProvenanceOf(historicalParent);
        if (model) return { model_type, model };
    }
    const dto = field_contract.native_dto_fields;
    if (dto && dto.model_type === model_type) {
        switch (dto.model_type) {
            case 'ReleaseInfo': {
                const datestamp = str(raw_fields, 'datestamp'), format_version = str(raw_fields, 'format_version');
                if (datestamp !== null && format_version !== null) return { model_type: 'ReleaseInfo', model: toInfo({ datestamp, format_version,
                    min_reader_version: str(raw_fields, 'min_reader_version'), concept_doi: str(raw_fields, 'concept_doi'), zenodo_version_doi: str(raw_fields, 'zenodo_version_doi'),
                    content_sha256: str(raw_fields, 'content_sha256'), files: Array.from(dto.context.files) }) };
                break;
            }
            case 'FileInfo': {
                const name = str(raw_fields, 'name'), size = num(raw_fields, 'size'), sha = str(raw_fields, 'sha256');
                if (name !== null && size !== null && sha !== null) return { model_type: 'FileInfo', model: fileInfoOf(name, dto.context.href, size, sha) };
                break;
            }
            case 'Nearby': {
                const distance = num(raw_fields, 'distance_km');
                if (distance !== null) return { model_type: 'Nearby', model: nearbyOf(dto.context.station, distance) };
                break;
            }
            case 'UpdateResult': {
                const updated = raw_fields['updated'], from = str(raw_fields, 'from'), to = str(raw_fields, 'to');
                if (typeof updated === 'boolean' && from !== null && to !== null) return { model_type: 'UpdateResult', model: updateResultOf(updated, from, to) };
                break;
            }
            case 'Stats': {
                const { type, kind, country, source, qc_status } = raw_fields;
                if (isCounts(type) && isCounts(kind) && isCounts(country) && isCounts(source) && isCounts(qc_status)) return { model_type: 'Stats', model: statsOf(type, kind, country, source, qc_status) };
                break;
            }
        }
    }
    const prepared = field_contract.native_result_fields;
    if (prepared) {
        if (prepared.model_type !== model_type) throw new X.InvalidReleaseError('prepared native fields name a different model');
        switch (prepared.model_type) {
            case 'HeightPoint': return { model_type: prepared.model_type, model: new R.HeightPoint(prepared.fields) };
            case 'Extreme': return { model_type: prepared.model_type, model: new R.Extreme(prepared.fields) };
            case 'CurrentPoint': return { model_type: prepared.model_type, model: new R.CurrentPoint(prepared.fields) };
            case 'CurrentEvent': return { model_type: prepared.model_type, model: new R.CurrentEvent(prepared.fields) };
            case 'HeightSeries': return { model_type: prepared.model_type, model: new R.HeightSeries(prepared.fields) };
            case 'ExtremeList': return { model_type: prepared.model_type, model: new R.ExtremeList(prepared.fields) };
            case 'CurrentSeries': return { model_type: prepared.model_type, model: new R.CurrentSeries(prepared.fields) };
            case 'CurrentEventList': return { model_type: prepared.model_type, model: new R.CurrentEventList(prepared.fields) };
            case 'DatumInfo': return { model_type: prepared.model_type, model: new R.DatumInfo(prepared.fields) };
            case 'DatumLevel': return { model_type: prepared.model_type, model: new R.DatumLevel(prepared.fields) };
            case 'Ranges': return { model_type: prepared.model_type, model: new R.Ranges(prepared.fields) };
        }
    }
    throw new CanonicalUnimplementedError(`B07 native owner ${model_type}`);
}

function isCounts(value: unknown): value is Readonly<Record<string, number>> {
    return isObject(value) && Object.values(value).every(item => typeof item === 'number');
}

export function access_raw_record(access_kind: C.access_kind, source_record: C.source_record, station: C.station, release_origin: C.release_origin, native_profile: C.native_profile): C.raw_record_or_valid_station {
    throw new CanonicalUnimplementedError("B08");
}

export async function open_client_release(operation_arguments: C.arguments, environment: C.environment, platform_defaults: C.platform_defaults, cache_state: C.cache_state, clock: C.clock, native_profile: C.native_profile, reader_version: C.reader_version): Promise<C.client_and_release> {
    throw new CanonicalUnimplementedError("B09");
}

export async function resolve_release_request(release_request: C.release_request, effective_options: C.effective_options, cache_state: C.cache_state, clock: C.clock, reader_version: C.reader_version): Promise<C.loaded_release> {
    throw new CanonicalUnimplementedError("B10");
}

export async function exchange_release_metadata(metadata_request: C.metadata_request, trusted_cache: C.trusted_cache, transport_options: C.transport_options, cache_state: C.cache_state, clock: C.clock, reader_version: C.reader_version): Promise<C.validated_metadata> {
    throw new CanonicalUnimplementedError("B11");
}

export async function update_client_release(client_state: C.client_state, update_request: C.update_request, clock: C.clock, reader_version: C.reader_version): Promise<C.updated_client_state> {
    throw new CanonicalUnimplementedError("B12");
}

export async function refresh_client_if_due(client_state: C.client_state, query_kind: C.query_kind, clock: C.clock, reader_version: C.reader_version): Promise<C.query_client_state> {
    throw new CanonicalUnimplementedError("B13");
}

export function forward_held_release(held_release: C.held_release, query_arguments: C.query_arguments): C.held_release_result {
    throw new CanonicalUnimplementedError("B14");
}

export function enforce_resource_lifetime(resource_state: C.resource_state, lifetime_action: C.lifetime_action): C.resource_state_or_error {
    throw new CanonicalUnimplementedError("B15");
}

export function bind_checksum_manifest(checksum_bytes: C.checksum_bytes, pointer_digests: C.pointer_digests, required_files: C.required_files): C.bound_checksums {
    throw new CanonicalUnimplementedError("B16");
}

export async function acquire_release_files(acquisition_descriptor: C.acquisition_descriptor, effective_options: C.effective_options, load_mode: C.load_mode, cache_state: C.cache_state, clock: C.clock, reader_version: C.reader_version): Promise<C.loaded_release> {
    throw new CanonicalUnimplementedError("B17");
}

export function merge_cache_receipt(locked_cache_state: C.locked_cache_state, verified_file_rows: C.verified_file_rows, release_metadata: C.release_metadata): C.merged_receipt {
    throw new CanonicalUnimplementedError("B18");
}

export async function select_cached_release(release_candidates: C.release_candidates, effective_options: C.effective_options, cache_state: C.cache_state, clock: C.clock): Promise<C.usable_cached_release_or_error> {
    throw new CanonicalUnimplementedError("B19");
}

export async function verify_release_files(release_files: C.release_files, trusted_cached_pointer: C.trusted_cached_pointer): Promise<C.verification_result> {
    throw new CanonicalUnimplementedError("B20");
}

export async function publish_download(destination: C.destination, format_selection: C.format_selection, overwrite_policy: C.overwrite_policy, release_files: C.release_files, checksum_bytes: C.checksum_bytes, pointer_digests: C.pointer_digests): Promise<C.download_result> {
    throw new CanonicalUnimplementedError("B21");
}

export async function manage_cache_inventory(inventory_action: C.inventory_action, cache_state: C.cache_state, keep: C.keep, current_cache_directory: C.current_cache_directory, clock: C.clock): Promise<C.cache_inventory_result> {
    throw new CanonicalUnimplementedError("B22");
}

export async function perform_guarded_io(io_kind: C.io_kind, io_request: C.io_request, io_options: C.io_options, clock: C.clock): Promise<C.io_result> {
    throw new CanonicalUnimplementedError("B23");
}

export function project_station_index(station_source_row: C.station_source_row, source_byte_span: C.source_byte_span, projection_contract: C.projection_contract): C.station_index_entry {
    const header = projection_contract.native_header;
    if (!header) throw new CanonicalUnimplementedError('B24 requires the authenticated native header');
    return indexDoc(station_source_row, header, source_byte_span.offset_bytes, source_byte_span.length_bytes,
        new Set(header.conventions.map(row => String(row['convention_id']))), new Set(header.licences.map(row => String(row['licence_id'])))).stored;
}

export async function authenticate_station_index(source_files: C.source_files, supplied_index: C.supplied_index, index_presence: C.index_presence, reader_version: C.reader_version): Promise<C.authenticated_index> {
    throw new CanonicalUnimplementedError("B25");
}

export function compare_station_source(index_entry: C.index_entry, station_source_row: C.station_source_row, index_presence: C.index_presence): C.compared_station_row {
    throw new CanonicalUnimplementedError("B26");
}

export function read_station_lazily(stream_reader: C.stream_reader, station_id: C.station_id, release_origin: C.release_origin, reader_version: C.reader_version): C.station_source_row {
    throw new CanonicalUnimplementedError("B27");
}

export function encode_cache_json(cache_document: C.cache_document): C.cache_bytes {
    return encodeCacheJson(cache_document.value);
}

export function lookup_station_identity(release_view: C.release_view, identity_query: C.identity_query, reader_version: C.reader_version): C.station_or_tombstone_or_null {
    throw new CanonicalUnimplementedError("B29");
}

export function select_effective_recommendation(station_sets: C.station_sets, original_recommendation: C.original_recommendation, commercial_only: C.commercial_only): C.effective_recommendation {
    throw new CanonicalUnimplementedError("B30");
}

export function admit_quality_path(candidate_path: C.candidate_path, include_flagged: C.include_flagged, include_fallback: C.include_fallback): C.quality_admission {
    throw new CanonicalUnimplementedError("B31");
}

export function admit_commercial_path(candidate_path: C.candidate_path, commercial_only: C.commercial_only, commercial_basis: C.commercial_basis): C.commercial_admission {
    throw new CanonicalUnimplementedError("B32");
}

export function resolve_reference_path(station_source_row: C.station_source_row, path_request: C.path_request, release_view: C.release_view): C.selected_reference_path {
    throw new CanonicalUnimplementedError("B33");
}

export function execute_discovery_query(release_view: C.release_view, query_kind: C.query_kind, query_options: C.query_options, reader_version: C.reader_version): C.ordered_station_results {
    throw new CanonicalUnimplementedError("B34");
}

export function summarize_station_sets(summary_kind: C.summary_kind, release_view: C.release_view, station_sets: C.station_sets, summary_options: C.summary_options): C.station_summary {
    throw new CanonicalUnimplementedError("B35");
}

export function admit_historical_offset(own_offset: C.own_offset, reference_path: C.reference_path, historical_policy: C.historical_policy, selection_kind: C.selection_kind, reader_version: C.reader_version): C.historical_admission {
    throw new CanonicalUnimplementedError("B36");
}

export function format_attribution(station: C.station, release_view: C.release_view, commercial_only: C.commercial_only): C.attribution_text {
    throw new CanonicalUnimplementedError("B37");
}

export function format_citation(published_metadata: C.published_metadata, citation_style: C.citation_style): C.citation_text {
    throw new CanonicalUnimplementedError("B38");
}

export function parse_prediction_window(time_inputs: C.time_inputs, window_inputs: C.window_inputs, step: C.step, local_time_profile: C.local_time_profile): C.prediction_window {
    const member = window_inputs.member_id;
    if (member === 'Release.heights' || member === 'Release.extremes' || member === 'Release.currents' || member === 'Release.current_events') {
        const args = window_inputs.arguments;
        const [start, stop] = nativeWindow(args.start, args.stop, member === 'Release.heights' || member === 'Release.currents' ? step : undefined);
        return { start, stop, step: member === 'Release.heights' || member === 'Release.currents' ? step : null };
    }
    if (time_inputs.member_id === 'Release.heights_at') return { instants: predictionSeconds(time_inputs.arguments.times) };
    throw new CanonicalUnimplementedError(`B39 native time member ${member}`);
}

export function select_prediction_model(station_request: C.station_request, release_view: C.release_view, selection_options: C.selection_options, reader_version: C.reader_version): C.selected_prediction_model {
    throw new CanonicalUnimplementedError("B40");
}

export function evaluate_astronomy(selected_prediction_model: C.selected_prediction_model, utc_instant: C.utc_instant): C.astronomical_terms {
    const model = selected_prediction_model, year = utc(utc_instant).getUTCFullYear();
    const table = nativeTable(model);
    const total = model.native_sum ?? new Sum(table, model.required_constituents.filter(isObject), { mean: model.mean_term });
    const [origin, constituent_terms] = total.yearData(year);
    return { utc_year: year, epoch_hours: (utc_instant - origin) / 3600, constituent_terms };
}

export function evaluate_harmonic_height(selected_prediction_model: C.selected_prediction_model, prediction_instants: C.prediction_instants, requested_datum: C.requested_datum): C.height_values {
    const model = selected_prediction_model, context = contextFor(model.station, model.constant_set, nativeTable(model));
    context.total = new Sum(context.table, model.required_constituents.filter(isObject));
    context.total.mean = datumTerm(isObject(model.datum_source) ? model.datum_source : null, requested_datum, context);
    for (const at of prediction_instants) evaluate_astronomy(model, at);
    return prediction_instants.map(at => context.total.value(at));
}

export function find_tide_events(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window): C.tide_events {
    throw new CanonicalUnimplementedError("B43");
}

export function evaluate_direct_current(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window, current_request: C.current_request, current_operation: C.current_operation): C.direct_current_result {
    throw new CanonicalUnimplementedError("B44");
}

export function evaluate_tide_offset(own_offset: C.own_offset, reference_path: C.reference_path, prediction_window: C.prediction_window, tide_request: C.tide_request, reader_version: C.reader_version): C.offset_tide_result {
    throw new CanonicalUnimplementedError("B45");
}

export function fold_equal_tide_offset(own_offset: C.own_offset, reference_model: C.reference_model, prediction_instants: C.prediction_instants, requested_datum: C.requested_datum): C.folded_height_values {
    throw new CanonicalUnimplementedError("B46");
}

export function evaluate_current_offset(own_current_offsets: C.own_current_offsets, reference_path: C.reference_path, prediction_window: C.prediction_window, current_request: C.current_request, reader_version: C.reader_version): C.offset_current_result {
    throw new CanonicalUnimplementedError("B47");
}

export function dispatch_auxiliary_result(auxiliary_kind: C.auxiliary_kind, auxiliary_operation: C.auxiliary_operation, source_values: C.source_values, result_context: C.result_context, local_time_profile: C.local_time_profile, result_values: C.result_values, utc_result: C.utc_result, selection_options: C.selection_options, reader_version: C.reader_version, auxiliary_member_id: C.auxiliary_member_id): C.auxiliary_result {
    throw new CanonicalUnimplementedError("B48");
}

export function retain_raw_source_record(source_record: C.source_record, native_profile: C.native_profile): C.raw_record {
    return deepFreeze(source_record);
}

export function check_station_origin(station: C.station, release_origin: C.release_origin): C.valid_station {
    throw new CanonicalUnimplementedError("B08.origin");
}

export async function manage_cache_lock(lock_request: C.lock_request, lock_state: C.lock_state, clock: C.clock): Promise<C.lock_outcome> {
    throw new CanonicalUnimplementedError("B23.lock");
}

export async function request_http_resource(http_request: C.http_request, transport_options: C.transport_options): Promise<C.http_response> {
    throw new CanonicalUnimplementedError("B23.http");
}

export function count_release_statistics(release_view: C.release_view): C.release_statistics {
    throw new CanonicalUnimplementedError("B35.stats");
}

export function order_constant_sets(station_sets: C.station_sets, original_recommendation: C.original_recommendation, commercial_only: C.commercial_only, include_no_constants: C.include_no_constants): C.ordered_constant_sets {
    throw new CanonicalUnimplementedError("B35.sets");
}

export function read_auxiliary_model_value(auxiliary_operation: C.auxiliary_operation, source_values: C.source_values, selection_options: C.selection_options, reader_version: C.reader_version, auxiliary_member_id: C.auxiliary_member_id): C.auxiliary_model_value {
    throw new CanonicalUnimplementedError("B48.aux");
}

export function construct_prediction_result(result_values: C.result_values, result_context: C.result_context): C.prediction_result {
    throw new CanonicalUnimplementedError("B48.context");
}

export function convert_result_to_local_time(utc_result: C.utc_result, local_time_profile: C.local_time_profile): C.local_time_result {
    throw new CanonicalUnimplementedError("B48.local");
}

export function find_unrounded_tide_events(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window): C.unrounded_tide_events {
    if (!('start' in prediction_window)) throw new X.InvalidArgumentError('tide roots require a prediction span');
    const model = selected_prediction_model, total = new Sum(nativeTable(model), model.required_constituents.filter(isObject), { mean: model.mean_term });
    return unroundedEvents(total, prediction_window.start, prediction_window.stop).map(([root_seconds, kind, height_m], reference_order) => {
        if (kind !== 'high' && kind !== 'low') throw new X.InvalidReleaseError('unexpected tide root kind');
        return { root_seconds, event_type: kind, height_m, reference_order };
    });
}

export function find_unrounded_current_events(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window, current_request: C.current_request): C.unrounded_current_events {
    if (!('start' in prediction_window)) throw new X.InvalidArgumentError('current roots require a prediction span');
    const model = selected_prediction_model, context = contextFor(model.station, model.constant_set, nativeTable(model));
    const requested = current_request.member_id === 'Release.current_events' || current_request.member_id === 'Release.currents' ? current_request.arguments.bin_number : model.reference_bin;
    const bins = arr(model.constant_set.raw, 'current_bins').filter(isObject);
    currentContext(context, bin(model.station, bins, requested));
    return unroundedCurrentEventsFor(context, prediction_window.start, prediction_window.stop).map(([root_seconds, event_type, velocity_m_s, direction_deg], reference_order) => ({ root_seconds, event_type, velocity_m_s, direction_deg, reference_order }));
}

function nativeTable(model: C.selected_prediction_model): AstroTable {
    if (!isObject(model.astro_table)) throw new X.NoAstroTableError('selected model has no native astro table');
    if (str(model.astro_table, 'astro_table_id') !== str(model.constant_set.convention.raw, 'astro_table_id')) throw new CanonicalUnimplementedError('selected model requires its convention astro table');
    if (model.native_sum) {
        if (model.native_sum.table._raw !== model.astro_table) throw new CanonicalUnimplementedError('selected model requires its borrowed Sum table owner');
        return model.native_sum.table;
    }
    return new AstroTable(model.astro_table);
}

function nativeOpenOptions(args: C.MemberArguments['Client.open']): OpenOptions {
    return { release: args.release, file: args.file, cacheDir: args.cache_dir, offline: args.offline,
        mode: args.mode, baseUrl: args.base_url, timeout: args.timeout, proxy: args.proxy, caFile: args.ca_file,
        userAgent: args.user_agent, onNetworkError: args.on_network_error, autoUpdate: args.auto_update,
        updateInterval: args.update_interval, logger: args.logger, verifyOnOpen: args.verify_on_open,
        commercialOnly: args.commercial_only, commercialBasis: args.commercial_basis, historicalOffsetsPolicy: args.historical_offsets_policy };
}

export async function acquire_checksum_sidecar(acquisition_descriptor: C.acquisition_descriptor, effective_options: C.effective_options): Promise<C.checksum_bytes> {
    throw new CanonicalUnimplementedError("B17.sidecar");
}
