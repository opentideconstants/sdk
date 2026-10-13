"""Construction proof: candidate native entries, never runtime behavior acceptance."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python" / "src"))

# Candidate source-path setup intentionally precedes native imports, as in test_unit.py.
from opentideconstants import OpenTideConstants  # noqa: E402
from opentideconstants import _canonical as canonical  # noqa: E402
from opentideconstants import _canonical_types as types  # noqa: E402


def test_missing_checksum_seam_constructs_and_refuses():
    assert Path(canonical.__file__).resolve().is_relative_to(ROOT / "python" / "src")
    descriptor = types._ReleaseDescriptor(
        datestamp="20991231",
        files=(),
        checksum_bytes=None,
        pointer_digests={},
        required_file_request=None,
        metadata={},
    )
    options = types._EffectiveOptions()
    with pytest.raises(NotImplementedError, match="B17.sidecar construction-only"):
        canonical._acquire_checksum_sidecar(
            acquisition_descriptor=descriptor,
            effective_options=options,
        )


# Complete native construction consumers


@dataclass(frozen=True, slots=True)
class _Inputs:
    operation: types._COperation
    arguments: types._CArguments
    member_contract: types._CMemberContract
    explicit_options: types._CExplicitOptions
    environment: types._CEnvironment
    platform_defaults: types._CPlatformDefaults
    ordered_failures: types._COrderedFailures
    cause: types._CCause
    canonical_result: types._CCanonicalResult
    canonical_error: types._CCanonicalError
    native_profile: types._CNativeProfile
    source_bytes: types._CSourceBytes
    reader_version: types._CReaderVersion
    document_kind: types._CDocumentKind
    parsed_document: types._CParsedDocument
    required_links: types._CRequiredLinks
    raw_fields: types._CRawFields
    field_contract: types._CFieldContract
    origin: types._COrigin
    model_type: types._CModelType
    access_kind: types._CAccessKind
    source_record: types._CSourceRecord
    station: types._CStation
    release_origin: types._CReleaseOrigin
    cache_state: types._CCacheState
    clock: types._CClock
    release_request: types._CReleaseRequest
    effective_options: types._CEffectiveOptions
    metadata_request: types._CMetadataRequest
    trusted_cache: types._CTrustedCache
    transport_options: types._CTransportOptions
    client_state: types._CClientState
    update_request: types._CUpdateRequest
    query_kind: types._CQueryKind
    held_release: types._CHeldRelease
    query_arguments: types._CQueryArguments
    resource_state: types._CResourceState
    lifetime_action: types._CLifetimeAction
    checksum_bytes: types._CChecksumBytes
    pointer_digests: types._CPointerDigests
    required_files: types._CRequiredFiles
    acquisition_descriptor: types._CAcquisitionDescriptor
    load_mode: types._CLoadMode
    locked_cache_state: types._CLockedCacheState
    verified_file_rows: types._CVerifiedFileRows
    release_metadata: types._CReleaseMetadata
    release_candidates: types._CReleaseCandidates
    release_files: types._CReleaseFiles
    trusted_cached_pointer: types._CTrustedCachedPointer
    destination: types._CDestination
    format_selection: types._CFormatSelection
    overwrite_policy: types._COverwritePolicy
    inventory_action: types._CInventoryAction
    keep: types._CKeep
    current_cache_directory: types._CCurrentCacheDirectory
    io_kind: types._CIoKind
    io_request: types._CIoRequest
    io_options: types._CIoOptions
    station_source_row: types._CStationSourceRow
    source_byte_span: types._CSourceByteSpan
    projection_contract: types._CProjectionContract
    source_files: types._CSourceFiles
    supplied_index: types._CSuppliedIndex
    index_presence: types._CIndexPresence
    index_entry: types._CIndexEntry
    stream_reader: types._CStreamReader
    station_id: types._CStationId
    cache_document: types._CCacheDocument
    release_view: types._CReleaseView
    identity_query: types._CIdentityQuery
    station_sets: types._CStationSets
    original_recommendation: types._COriginalRecommendation
    commercial_only: types._CCommercialOnly
    candidate_path: types._CCandidatePath
    include_flagged: types._CIncludeFlagged
    include_fallback: types._CIncludeFallback
    commercial_basis: types._CCommercialBasis
    path_request: types._CPathRequest
    query_options: types._CQueryOptions
    summary_kind: types._CSummaryKind
    summary_options: types._CSummaryOptions
    own_offset: types._COwnOffset
    reference_path: types._CReferencePath
    historical_policy: types._CHistoricalPolicy
    selection_kind: types._CSelectionKind
    published_metadata: types._CPublishedMetadata
    citation_style: types._CCitationStyle
    time_inputs: types._CTimeInputs
    window_inputs: types._CWindowInputs
    step: types._CStep
    local_time_profile: types._CLocalTimeProfile
    station_request: types._CStationRequest
    selection_options: types._CSelectionOptions
    selected_prediction_model: types._CSelectedPredictionModel
    utc_instant: types._CUtcInstant
    prediction_instants: types._CPredictionInstants
    requested_datum: types._CRequestedDatum
    prediction_window: types._CPredictionWindow
    current_request: types._CCurrentRequest
    current_operation: types._CCurrentOperation
    tide_request: types._CTideRequest
    reference_model: types._CReferenceModel
    own_current_offsets: types._COwnCurrentOffsets
    auxiliary_kind: types._CAuxiliaryKind
    auxiliary_operation: types._CAuxiliaryOperation
    source_values: types._CSourceValues
    result_context: types._CResultContext
    result_values: types._CResultValues
    utc_result: types._CUtcResult
    auxiliary_member_id: types._CAuxiliaryMemberId
    lock_request: types._CLockRequest
    lock_state: types._CLockState
    http_request: types._CHttpRequest
    include_no_constants: types._CIncludeNoConstants


@pytest.fixture(scope="session")
def inputs() -> Iterator[_Inputs]:
    build = ROOT / "python" / "dist" / "canonical-shape"
    build.mkdir(parents=True, exist_ok=True)
    (build / "invocations.jsonl").write_text("", encoding="utf-8")
    with OpenTideConstants(
        file=ROOT / "conformance" / "fixtures" / "good" / "OTC_20991231.json"
    ) as client:
        release = client.release
        station = release.require_station("OTC-T-0001")
        constants = station.recommended_set
        assert constants is not None
        tombstone = release.tombstone("OTC-T-0005")
        assert tombstone is not None
        yield _Inputs(
            operation="astro_table",
            arguments=types._Arguments0(
                member_id="Client.open",
                release=types._OMITTED,
                file=None,
                cache_dir=None,
                offline=types._OMITTED,
                mode=types._OMITTED,
                base_url=types._OMITTED,
                timeout=None,
                proxy=None,
                ca_file=None,
                user_agent=None,
                on_network_error=types._OMITTED,
                auto_update=types._OMITTED,
                update_interval=types._OMITTED,
                logger=None,
                verify_on_open=types._OMITTED,
                commercial_only=types._OMITTED,
                commercial_basis=types._OMITTED,
                historical_offsets_policy=types._OMITTED,
            ),
            member_contract=types._Arguments0(
                member_id="Client.open",
                release=types._OMITTED,
                file=None,
                cache_dir=None,
                offline=types._OMITTED,
                mode=types._OMITTED,
                base_url=types._OMITTED,
                timeout=None,
                proxy=None,
                ca_file=None,
                user_agent=None,
                on_network_error=types._OMITTED,
                auto_update=types._OMITTED,
                update_interval=types._OMITTED,
                logger=None,
                verify_on_open=types._OMITTED,
                commercial_only=types._OMITTED,
                commercial_basis=types._OMITTED,
                historical_offsets_policy=types._OMITTED,
            ),
            explicit_options=types._EffectiveOptions(),
            environment={},
            platform_defaults=types._EffectiveOptions(),
            ordered_failures=(),
            cause=None,
            canonical_result=types._Absent(),
            canonical_error=types._Absent(),
            native_profile="python",
            source_bytes=b"",
            reader_version=types._ReaderVersion(major=1, minor=1),
            document_kind="release",
            parsed_document={},
            required_links=types._RequiredLinks(
                conventions={}, licences={}, station_ids=(), constituent_names=()
            ),
            raw_fields={},
            field_contract=(),
            origin=types._OpaqueOrigin(),
            model_type="Client",
            access_kind="raw_record",
            source_record={},
            station=station,
            release_origin=types._OpaqueOrigin(),
            cache_state=types._CacheState(
                cache_root=Path("construction"),
                release_candidates=(),
                pointer_cache=None,
                lock_state=types._LockState(
                    cache_root=Path("construction"), owner=None, held_token=None
                ),
            ),
            clock=1.0,
            release_request="latest",
            effective_options=types._EffectiveOptions(),
            metadata_request=types._MetadataRequest(
                request_url="construction", document_kind="construction"
            ),
            trusted_cache=None,
            transport_options=types._TransportOptions(),
            client_state=types._ClientState(
                current_release=release,
                effective_options=types._EffectiveOptions(),
                cache_state=types._CacheState(
                    cache_root=Path("construction"),
                    release_candidates=(),
                    pointer_cache=None,
                    lock_state=types._LockState(
                        cache_root=Path("construction"), owner=None, held_token=None
                    ),
                ),
                last_error=None,
                last_update_check=None,
                closed=False,
            ),
            update_request=types._MetadataRequest(
                request_url="construction", document_kind="construction"
            ),
            query_kind="stations",
            held_release=release,
            query_arguments=types._Arguments0(
                member_id="Client.open",
                release=types._OMITTED,
                file=None,
                cache_dir=None,
                offline=types._OMITTED,
                mode=types._OMITTED,
                base_url=types._OMITTED,
                timeout=None,
                proxy=None,
                ca_file=None,
                user_agent=None,
                on_network_error=types._OMITTED,
                auto_update=types._OMITTED,
                update_interval=types._OMITTED,
                logger=None,
                verify_on_open=types._OMITTED,
                commercial_only=types._OMITTED,
                commercial_basis=types._OMITTED,
                historical_offsets_policy=types._OMITTED,
            ),
            resource_state=types._ClientState(
                current_release=release,
                effective_options=types._EffectiveOptions(),
                cache_state=types._CacheState(
                    cache_root=Path("construction"),
                    release_candidates=(),
                    pointer_cache=None,
                    lock_state=types._LockState(
                        cache_root=Path("construction"), owner=None, held_token=None
                    ),
                ),
                last_error=None,
                last_update_check=None,
                closed=False,
            ),
            lifetime_action="construction",
            checksum_bytes=b"",
            pointer_digests={},
            required_files=(),
            acquisition_descriptor=types._ReleaseDescriptor(
                datestamp="construction",
                files=(),
                checksum_bytes=None,
                pointer_digests={},
                required_file_request=None,
                metadata={},
            ),
            load_mode="eager",
            locked_cache_state=types._CacheState(
                cache_root=Path("construction"),
                release_candidates=(),
                pointer_cache=None,
                lock_state=types._LockState(
                    cache_root=Path("construction"), owner=None, held_token=None
                ),
            ),
            verified_file_rows=(),
            release_metadata={},
            release_candidates=(),
            release_files=(),
            trusted_cached_pointer=None,
            destination=Path("construction"),
            format_selection=types._FormatSelection(formats=(), required_files=()),
            overwrite_policy=(),
            inventory_action="list",
            keep=1,
            current_cache_directory=Path("construction"),
            io_kind="lock",
            io_request=types._LockRequest(
                directory=Path("construction"), operation="take", token=None
            ),
            io_options=types._LockState(
                cache_root=Path("construction"), owner=None, held_token=None
            ),
            station_source_row={},
            source_byte_span=types._SourceByteSpan(offset_bytes=1, length_bytes=1),
            projection_contract=types._ProjectionContract(
                "Exact original canonical field table attached per member; known wrong type is invalid_release, absent nullable is null, missing arrays use each attached contract default. Raw fields preserve source JSON without computed fields.",
                "Model IDs refer to B07, source/ownership objects also B08, historical fields B36, prediction/local/datum results B48. These are value projection behaviors, not an assertion that every getter has an independent algorithm.",
                "Complete source object, including all unknown nested fields, represented by tolerant cache-specific definitions derived from accepted schema33a760ad. Known primitive types, required historical fields, source binding conditions and raw values remain unchanged.",
                "25 scenario families enumerate required shared branches. They are not 25 executed passes or exhaustive binary-branch verification. Each family expands to its incorporated original case table and required additional guard-reaching witnesses.",
                "Complete actual fallback object, including unknown nested fields. String reasons remain source strings in cache/raw and become typed other when unknown. Cache-source comparison includes every preserved field, not only current known keys.",
            ),
            source_files=types._SourceFiles(
                jsonl=Path("construction"),
                meta=Path("construction"),
                jsonl_sha256="construction",
                jsonl_size=1,
                meta_sha256="construction",
                meta_size=1,
            ),
            supplied_index=None,
            index_presence={},
            index_entry={
                "station_id": "construction",
                "status": "construction",
                "name": None,
                "name_folded": None,
                "country": None,
                "type": None,
                "kind": None,
                "reference_station_id": None,
                "offsets_licence_id": None,
                "recommended_set_id": None,
                "lat": None,
                "lon": None,
                "offset": 1,
                "length": 1,
                "aliases": {},
                "sets": (),
                "subordinate_offsets": None,
                "current_offsets": (),
            },
            stream_reader=types._StreamReader(
                release_view=release,
                file_descriptor=1,
                index={},
                index_presence={},
                station_lru={},
                closed=False,
            ),
            station_id="construction",
            cache_document={
                "index_version": 1,
                "discovery_index_version": 1,
                "datestamp": "construction",
                "jsonl": "construction",
                "jsonl_sha256": "construction",
                "jsonl_size": 1,
                "by": "construction",
                "stations": (),
            },
            release_view=release,
            identity_query="construction",
            station_sets=(),
            original_recommendation=None,
            commercial_only=False,
            candidate_path=types._CandidatePathVariant0(
                station=station, constant_set=constants, release_view=release
            ),
            include_flagged=False,
            include_fallback=False,
            commercial_basis="strict",
            path_request="construction",
            query_options=types._Arguments8(
                member_id="Release.stations",
                country=None,
                type=None,
                kind=None,
                source=None,
                source_type=None,
                include_flagged=types._OMITTED,
                include_fallback=types._OMITTED,
            ),
            summary_kind="stats",
            summary_options=types._SummaryOptions(
                original_recommendation=None,
                commercial_only=False,
                include_no_constants=False,
            ),
            own_offset=None,
            reference_path=types._ReferencePath(
                station=station,
                release_view=release,
                constant_set=None,
                own_offset=None,
                reference_bin=None,
            ),
            historical_policy="fallback",
            selection_kind="discovery",
            published_metadata=types._PublishedMetadata(
                contributors={},
                year=1,
                concept_doi=None,
                zenodo_version_doi=None,
                dataset_url="construction",
            ),
            citation_style="construction",
            time_inputs=types._Arguments0(
                member_id="Client.open",
                release=types._OMITTED,
                file=None,
                cache_dir=None,
                offline=types._OMITTED,
                mode=types._OMITTED,
                base_url=types._OMITTED,
                timeout=None,
                proxy=None,
                ca_file=None,
                user_agent=None,
                on_network_error=types._OMITTED,
                auto_update=types._OMITTED,
                update_interval=types._OMITTED,
                logger=None,
                verify_on_open=types._OMITTED,
                commercial_only=types._OMITTED,
                commercial_basis=types._OMITTED,
                historical_offsets_policy=types._OMITTED,
            ),
            window_inputs=types._Arguments0(
                member_id="Client.open",
                release=types._OMITTED,
                file=None,
                cache_dir=None,
                offline=types._OMITTED,
                mode=types._OMITTED,
                base_url=types._OMITTED,
                timeout=None,
                proxy=None,
                ca_file=None,
                user_agent=None,
                on_network_error=types._OMITTED,
                auto_update=types._OMITTED,
                update_interval=types._OMITTED,
                logger=None,
                verify_on_open=types._OMITTED,
                commercial_only=types._OMITTED,
                commercial_basis=types._OMITTED,
                historical_offsets_policy=types._OMITTED,
            ),
            step=types._OMITTED,
            local_time_profile=types._LocalTimeProfile(),
            station_request=station,
            selection_options=types._SelectionOptions(),
            selected_prediction_model=types._PredictionModel(
                station=station,
                release_view=release,
                constant_set=constants,
                convention=constants.convention,
                astro_table={},
                required_constituents=(),
                reference_bin=None,
                mean_term=1.0,
                datum_source=None,
            ),
            utc_instant=1.0,
            prediction_instants=(),
            requested_datum="construction",
            prediction_window=types._PredictionWindow(
                start=1.0, stop=1.0, step=None, instants=None
            ),
            current_request=types._Arguments0(
                member_id="Client.open",
                release=types._OMITTED,
                file=None,
                cache_dir=None,
                offline=types._OMITTED,
                mode=types._OMITTED,
                base_url=types._OMITTED,
                timeout=None,
                proxy=None,
                ca_file=None,
                user_agent=None,
                on_network_error=types._OMITTED,
                auto_update=types._OMITTED,
                update_interval=types._OMITTED,
                logger=None,
                verify_on_open=types._OMITTED,
                commercial_only=types._OMITTED,
                commercial_basis=types._OMITTED,
                historical_offsets_policy=types._OMITTED,
            ),
            current_operation="currents",
            tide_request=types._Arguments0(
                member_id="Client.open",
                release=types._OMITTED,
                file=None,
                cache_dir=None,
                offline=types._OMITTED,
                mode=types._OMITTED,
                base_url=types._OMITTED,
                timeout=None,
                proxy=None,
                ca_file=None,
                user_agent=None,
                on_network_error=types._OMITTED,
                auto_update=types._OMITTED,
                update_interval=types._OMITTED,
                logger=None,
                verify_on_open=types._OMITTED,
                commercial_only=types._OMITTED,
                commercial_basis=types._OMITTED,
                historical_offsets_policy=types._OMITTED,
            ),
            reference_model=types._PredictionModel(
                station=station,
                release_view=release,
                constant_set=constants,
                convention=constants.convention,
                astro_table={},
                required_constituents=(),
                reference_bin=None,
                mean_term=1.0,
                datum_source=None,
            ),
            own_current_offsets=None,
            auxiliary_kind="model_access",
            auxiliary_operation="astro_table",
            source_values=types._AuxiliaryValuesVariant0(
                station_request=station,
                release_view=release,
                selection_options=types._SelectionOptions(),
                utc_instant=None,
            ),
            result_context=types._ResultContext(
                station_id="construction",
                set_id=None,
                reference_station_id=None,
                bin_number=None,
                datum=None,
                release_datestamp="construction",
                algorithm="construction",
            ),
            result_values=types._MemberValue0(member_id="Client.open", value=client),
            utc_result=types._MemberValue0(member_id="Client.open", value=client),
            auxiliary_member_id="Client.open",
            lock_request=types._LockRequest(
                directory=Path("construction"), operation="take", token=None
            ),
            lock_state=types._LockState(
                cache_root=Path("construction"), owner=None, held_token=None
            ),
            http_request=types._HttpRequest(url="construction", conditional_etag=None),
            include_no_constants=False,
        )


def _record_entry(
    identifier: str, refusal: NotImplementedError, arguments: Mapping[str, str]
) -> None:
    trace = refusal.__traceback__
    observed = None
    while trace is not None:
        if (
            Path(trace.tb_frame.f_code.co_filename).resolve()
            == Path(canonical.__file__).resolve()
        ):
            observed = trace.tb_frame
        trace = trace.tb_next
    assert observed is not None, (
        "Refusal must originate in the actual candidate SDK entry"
    )
    actual = {name: repr(observed.f_locals[name]) for name in arguments}
    assert actual == arguments, (
        "Native arguments must be the owned typed fixture values"
    )
    source = Path(observed.f_code.co_filename).resolve()
    assert source.is_relative_to(ROOT / "python" / "src")
    lines = source.read_text(encoding="utf-8").splitlines()
    first = observed.f_code.co_firstlineno - 1
    last = first
    while not lines[last].endswith(":"):
        last += 1
    signature = "\n".join(lines[first : last + 1])
    entry = "opentideconstants._canonical." + observed.f_code.co_name
    payload = {
        "id": identifier,
        "native_entry": entry,
        "signature": signature,
        "arguments": actual,
        "refusal": str(refusal),
        "module": str(source),
        "line": observed.f_code.co_firstlineno,
        "cached_module": canonical.__cached__,
        "cleanup": "call-bounded native strong references; no acquired resource or result survives refusal",
    }
    with (ROOT / "python" / "dist" / "canonical-shape" / "invocations.jsonl").open(
        "a", encoding="utf-8"
    ) as evidence:
        evidence.write(json.dumps(payload, sort_keys=True) + "\n")


def test_construction_B01(inputs: _Inputs) -> None:
    try:
        canonical._validate_operation_arguments(
            operation=inputs.operation,
            arguments=inputs.arguments,
            member_contract=inputs.member_contract,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B01",
            refusal,
            {
                "operation": repr(inputs.operation),
                "arguments": repr(inputs.arguments),
                "member_contract": repr(inputs.member_contract),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B02(inputs: _Inputs) -> None:
    try:
        canonical._resolve_effective_options(
            explicit_options=inputs.explicit_options,
            environment=inputs.environment,
            platform_defaults=inputs.platform_defaults,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B02",
            refusal,
            {
                "explicit_options": repr(inputs.explicit_options),
                "environment": repr(inputs.environment),
                "platform_defaults": repr(inputs.platform_defaults),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B03(inputs: _Inputs) -> None:
    try:
        canonical._select_canonical_error(
            operation=inputs.operation,
            ordered_failures=inputs.ordered_failures,
            cause=inputs.cause,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B03",
            refusal,
            {
                "operation": repr(inputs.operation),
                "ordered_failures": repr(inputs.ordered_failures),
                "cause": repr(inputs.cause),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B04(inputs: _Inputs) -> None:
    try:
        canonical._translate_native_binding(
            canonical_result=inputs.canonical_result,
            canonical_error=inputs.canonical_error,
            native_profile=inputs.native_profile,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B04",
            refusal,
            {
                "canonical_result": repr(inputs.canonical_result),
                "canonical_error": repr(inputs.canonical_error),
                "native_profile": repr(inputs.native_profile),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B05(inputs: _Inputs) -> None:
    try:
        canonical._decode_release_document(
            source_bytes=inputs.source_bytes,
            reader_version=inputs.reader_version,
            document_kind=inputs.document_kind,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B05",
            refusal,
            {
                "source_bytes": repr(inputs.source_bytes),
                "reader_version": repr(inputs.reader_version),
                "document_kind": repr(inputs.document_kind),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B06(inputs: _Inputs) -> None:
    try:
        canonical._validate_release_links(
            parsed_document=inputs.parsed_document, required_links=inputs.required_links
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B06",
            refusal,
            {
                "parsed_document": repr(inputs.parsed_document),
                "required_links": repr(inputs.required_links),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B07(inputs: _Inputs) -> None:
    try:
        canonical._materialize_typed_model(
            raw_fields=inputs.raw_fields,
            field_contract=inputs.field_contract,
            origin=inputs.origin,
            model_type=inputs.model_type,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B07",
            refusal,
            {
                "raw_fields": repr(inputs.raw_fields),
                "field_contract": repr(inputs.field_contract),
                "origin": repr(inputs.origin),
                "model_type": repr(inputs.model_type),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B08(inputs: _Inputs) -> None:
    try:
        canonical._access_raw_record(
            access_kind=inputs.access_kind,
            source_record=inputs.source_record,
            station=inputs.station,
            release_origin=inputs.release_origin,
            native_profile=inputs.native_profile,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B08",
            refusal,
            {
                "access_kind": repr(inputs.access_kind),
                "source_record": repr(inputs.source_record),
                "station": repr(inputs.station),
                "release_origin": repr(inputs.release_origin),
                "native_profile": repr(inputs.native_profile),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B09(inputs: _Inputs) -> None:
    try:
        canonical._open_client_release(
            arguments=inputs.arguments,
            environment=inputs.environment,
            platform_defaults=inputs.platform_defaults,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            native_profile=inputs.native_profile,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B09",
            refusal,
            {
                "arguments": repr(inputs.arguments),
                "environment": repr(inputs.environment),
                "platform_defaults": repr(inputs.platform_defaults),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "native_profile": repr(inputs.native_profile),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B10(inputs: _Inputs) -> None:
    try:
        canonical._resolve_release_request(
            release_request=inputs.release_request,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B10",
            refusal,
            {
                "release_request": repr(inputs.release_request),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B11(inputs: _Inputs) -> None:
    try:
        canonical._exchange_release_metadata(
            metadata_request=inputs.metadata_request,
            trusted_cache=inputs.trusted_cache,
            transport_options=inputs.transport_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B11",
            refusal,
            {
                "metadata_request": repr(inputs.metadata_request),
                "trusted_cache": repr(inputs.trusted_cache),
                "transport_options": repr(inputs.transport_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B12(inputs: _Inputs) -> None:
    try:
        canonical._update_client_release(
            client_state=inputs.client_state,
            update_request=inputs.update_request,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B12",
            refusal,
            {
                "client_state": repr(inputs.client_state),
                "update_request": repr(inputs.update_request),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B13(inputs: _Inputs) -> None:
    try:
        canonical._refresh_client_if_due(
            client_state=inputs.client_state,
            query_kind=inputs.query_kind,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B13",
            refusal,
            {
                "client_state": repr(inputs.client_state),
                "query_kind": repr(inputs.query_kind),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B14(inputs: _Inputs) -> None:
    try:
        canonical._forward_held_release(
            held_release=inputs.held_release, query_arguments=inputs.query_arguments
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B14",
            refusal,
            {
                "held_release": repr(inputs.held_release),
                "query_arguments": repr(inputs.query_arguments),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B15(inputs: _Inputs) -> None:
    try:
        canonical._enforce_resource_lifetime(
            resource_state=inputs.resource_state, lifetime_action=inputs.lifetime_action
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B15",
            refusal,
            {
                "resource_state": repr(inputs.resource_state),
                "lifetime_action": repr(inputs.lifetime_action),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B16(inputs: _Inputs) -> None:
    try:
        canonical._bind_checksum_manifest(
            checksum_bytes=inputs.checksum_bytes,
            pointer_digests=inputs.pointer_digests,
            required_files=inputs.required_files,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B16",
            refusal,
            {
                "checksum_bytes": repr(inputs.checksum_bytes),
                "pointer_digests": repr(inputs.pointer_digests),
                "required_files": repr(inputs.required_files),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17(inputs: _Inputs) -> None:
    try:
        canonical._acquire_release_files(
            acquisition_descriptor=inputs.acquisition_descriptor,
            effective_options=inputs.effective_options,
            load_mode=inputs.load_mode,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17",
            refusal,
            {
                "acquisition_descriptor": repr(inputs.acquisition_descriptor),
                "effective_options": repr(inputs.effective_options),
                "load_mode": repr(inputs.load_mode),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B18(inputs: _Inputs) -> None:
    try:
        canonical._merge_cache_receipt(
            locked_cache_state=inputs.locked_cache_state,
            verified_file_rows=inputs.verified_file_rows,
            release_metadata=inputs.release_metadata,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B18",
            refusal,
            {
                "locked_cache_state": repr(inputs.locked_cache_state),
                "verified_file_rows": repr(inputs.verified_file_rows),
                "release_metadata": repr(inputs.release_metadata),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B19(inputs: _Inputs) -> None:
    try:
        canonical._select_cached_release(
            release_candidates=inputs.release_candidates,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B19",
            refusal,
            {
                "release_candidates": repr(inputs.release_candidates),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B20(inputs: _Inputs) -> None:
    try:
        canonical._verify_release_files(
            release_files=inputs.release_files,
            trusted_cached_pointer=inputs.trusted_cached_pointer,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B20",
            refusal,
            {
                "release_files": repr(inputs.release_files),
                "trusted_cached_pointer": repr(inputs.trusted_cached_pointer),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B21(inputs: _Inputs) -> None:
    try:
        canonical._publish_download(
            destination=inputs.destination,
            format_selection=inputs.format_selection,
            overwrite_policy=inputs.overwrite_policy,
            release_files=inputs.release_files,
            checksum_bytes=inputs.checksum_bytes,
            pointer_digests=inputs.pointer_digests,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B21",
            refusal,
            {
                "destination": repr(inputs.destination),
                "format_selection": repr(inputs.format_selection),
                "overwrite_policy": repr(inputs.overwrite_policy),
                "release_files": repr(inputs.release_files),
                "checksum_bytes": repr(inputs.checksum_bytes),
                "pointer_digests": repr(inputs.pointer_digests),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B22(inputs: _Inputs) -> None:
    try:
        canonical._manage_cache_inventory(
            inventory_action=inputs.inventory_action,
            cache_state=inputs.cache_state,
            keep=inputs.keep,
            current_cache_directory=inputs.current_cache_directory,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B22",
            refusal,
            {
                "inventory_action": repr(inputs.inventory_action),
                "cache_state": repr(inputs.cache_state),
                "keep": repr(inputs.keep),
                "current_cache_directory": repr(inputs.current_cache_directory),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B23(inputs: _Inputs) -> None:
    try:
        canonical._perform_guarded_io(
            io_kind=inputs.io_kind,
            io_request=inputs.io_request,
            io_options=inputs.io_options,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B23",
            refusal,
            {
                "io_kind": repr(inputs.io_kind),
                "io_request": repr(inputs.io_request),
                "io_options": repr(inputs.io_options),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B24(inputs: _Inputs) -> None:
    try:
        canonical._project_station_index(
            station_source_row=inputs.station_source_row,
            source_byte_span=inputs.source_byte_span,
            projection_contract=inputs.projection_contract,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B24",
            refusal,
            {
                "station_source_row": repr(inputs.station_source_row),
                "source_byte_span": repr(inputs.source_byte_span),
                "projection_contract": repr(inputs.projection_contract),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B25(inputs: _Inputs) -> None:
    try:
        canonical._authenticate_station_index(
            source_files=inputs.source_files,
            supplied_index=inputs.supplied_index,
            index_presence=inputs.index_presence,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B25",
            refusal,
            {
                "source_files": repr(inputs.source_files),
                "supplied_index": repr(inputs.supplied_index),
                "index_presence": repr(inputs.index_presence),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B26(inputs: _Inputs) -> None:
    try:
        canonical._compare_station_source(
            index_entry=inputs.index_entry,
            station_source_row=inputs.station_source_row,
            index_presence=inputs.index_presence,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B26",
            refusal,
            {
                "index_entry": repr(inputs.index_entry),
                "station_source_row": repr(inputs.station_source_row),
                "index_presence": repr(inputs.index_presence),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B27(inputs: _Inputs) -> None:
    try:
        canonical._read_station_lazily(
            stream_reader=inputs.stream_reader,
            station_id=inputs.station_id,
            release_origin=inputs.release_origin,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B27",
            refusal,
            {
                "stream_reader": repr(inputs.stream_reader),
                "station_id": repr(inputs.station_id),
                "release_origin": repr(inputs.release_origin),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B28(inputs: _Inputs) -> None:
    try:
        canonical._encode_cache_json(cache_document=inputs.cache_document)
    except NotImplementedError as refusal:
        _record_entry("B28", refusal, {"cache_document": repr(inputs.cache_document)})
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B29(inputs: _Inputs) -> None:
    try:
        canonical._lookup_station_identity(
            release_view=inputs.release_view,
            identity_query=inputs.identity_query,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B29",
            refusal,
            {
                "release_view": repr(inputs.release_view),
                "identity_query": repr(inputs.identity_query),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B30(inputs: _Inputs) -> None:
    try:
        canonical._select_effective_recommendation(
            station_sets=inputs.station_sets,
            original_recommendation=inputs.original_recommendation,
            commercial_only=inputs.commercial_only,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B30",
            refusal,
            {
                "station_sets": repr(inputs.station_sets),
                "original_recommendation": repr(inputs.original_recommendation),
                "commercial_only": repr(inputs.commercial_only),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B31(inputs: _Inputs) -> None:
    try:
        canonical._admit_quality_path(
            candidate_path=inputs.candidate_path,
            include_flagged=inputs.include_flagged,
            include_fallback=inputs.include_fallback,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B31",
            refusal,
            {
                "candidate_path": repr(inputs.candidate_path),
                "include_flagged": repr(inputs.include_flagged),
                "include_fallback": repr(inputs.include_fallback),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B32(inputs: _Inputs) -> None:
    try:
        canonical._admit_commercial_path(
            candidate_path=inputs.candidate_path,
            commercial_only=inputs.commercial_only,
            commercial_basis=inputs.commercial_basis,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B32",
            refusal,
            {
                "candidate_path": repr(inputs.candidate_path),
                "commercial_only": repr(inputs.commercial_only),
                "commercial_basis": repr(inputs.commercial_basis),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B33(inputs: _Inputs) -> None:
    try:
        canonical._resolve_reference_path(
            station_source_row=inputs.station_source_row,
            path_request=inputs.path_request,
            release_view=inputs.release_view,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B33",
            refusal,
            {
                "station_source_row": repr(inputs.station_source_row),
                "path_request": repr(inputs.path_request),
                "release_view": repr(inputs.release_view),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B34(inputs: _Inputs) -> None:
    try:
        canonical._execute_discovery_query(
            release_view=inputs.release_view,
            query_kind=inputs.query_kind,
            query_options=inputs.query_options,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B34",
            refusal,
            {
                "release_view": repr(inputs.release_view),
                "query_kind": repr(inputs.query_kind),
                "query_options": repr(inputs.query_options),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B35(inputs: _Inputs) -> None:
    try:
        canonical._summarize_station_sets(
            summary_kind=inputs.summary_kind,
            release_view=inputs.release_view,
            station_sets=inputs.station_sets,
            summary_options=inputs.summary_options,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B35",
            refusal,
            {
                "summary_kind": repr(inputs.summary_kind),
                "release_view": repr(inputs.release_view),
                "station_sets": repr(inputs.station_sets),
                "summary_options": repr(inputs.summary_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B36(inputs: _Inputs) -> None:
    try:
        canonical._admit_historical_offset(
            own_offset=inputs.own_offset,
            reference_path=inputs.reference_path,
            historical_policy=inputs.historical_policy,
            selection_kind=inputs.selection_kind,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B36",
            refusal,
            {
                "own_offset": repr(inputs.own_offset),
                "reference_path": repr(inputs.reference_path),
                "historical_policy": repr(inputs.historical_policy),
                "selection_kind": repr(inputs.selection_kind),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B37(inputs: _Inputs) -> None:
    try:
        canonical._format_attribution(
            station=inputs.station,
            release_view=inputs.release_view,
            commercial_only=inputs.commercial_only,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B37",
            refusal,
            {
                "station": repr(inputs.station),
                "release_view": repr(inputs.release_view),
                "commercial_only": repr(inputs.commercial_only),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B38(inputs: _Inputs) -> None:
    try:
        canonical._format_citation(
            published_metadata=inputs.published_metadata,
            citation_style=inputs.citation_style,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B38",
            refusal,
            {
                "published_metadata": repr(inputs.published_metadata),
                "citation_style": repr(inputs.citation_style),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B39(inputs: _Inputs) -> None:
    try:
        canonical._parse_prediction_window(
            time_inputs=inputs.time_inputs,
            window_inputs=inputs.window_inputs,
            step=inputs.step,
            local_time_profile=inputs.local_time_profile,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B39",
            refusal,
            {
                "time_inputs": repr(inputs.time_inputs),
                "window_inputs": repr(inputs.window_inputs),
                "step": repr(inputs.step),
                "local_time_profile": repr(inputs.local_time_profile),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B40(inputs: _Inputs) -> None:
    try:
        canonical._select_prediction_model(
            station_request=inputs.station_request,
            release_view=inputs.release_view,
            selection_options=inputs.selection_options,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B40",
            refusal,
            {
                "station_request": repr(inputs.station_request),
                "release_view": repr(inputs.release_view),
                "selection_options": repr(inputs.selection_options),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B41(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B41",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "utc_instant": repr(inputs.utc_instant),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B42(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_harmonic_height(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_instants=inputs.prediction_instants,
            requested_datum=inputs.requested_datum,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B42",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_instants": repr(inputs.prediction_instants),
                "requested_datum": repr(inputs.requested_datum),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B43(inputs: _Inputs) -> None:
    try:
        canonical._find_tide_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B43",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B44(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_direct_current(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
            current_operation=inputs.current_operation,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B44",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
                "current_request": repr(inputs.current_request),
                "current_operation": repr(inputs.current_operation),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B45(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_tide_offset(
            own_offset=inputs.own_offset,
            reference_path=inputs.reference_path,
            prediction_window=inputs.prediction_window,
            tide_request=inputs.tide_request,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B45",
            refusal,
            {
                "own_offset": repr(inputs.own_offset),
                "reference_path": repr(inputs.reference_path),
                "prediction_window": repr(inputs.prediction_window),
                "tide_request": repr(inputs.tide_request),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B46(inputs: _Inputs) -> None:
    try:
        canonical._fold_equal_tide_offset(
            own_offset=inputs.own_offset,
            reference_model=inputs.reference_model,
            prediction_instants=inputs.prediction_instants,
            requested_datum=inputs.requested_datum,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B46",
            refusal,
            {
                "own_offset": repr(inputs.own_offset),
                "reference_model": repr(inputs.reference_model),
                "prediction_instants": repr(inputs.prediction_instants),
                "requested_datum": repr(inputs.requested_datum),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B47(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_current_offset(
            own_current_offsets=inputs.own_current_offsets,
            reference_path=inputs.reference_path,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B47",
            refusal,
            {
                "own_current_offsets": repr(inputs.own_current_offsets),
                "reference_path": repr(inputs.reference_path),
                "prediction_window": repr(inputs.prediction_window),
                "current_request": repr(inputs.current_request),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48(inputs: _Inputs) -> None:
    try:
        canonical._dispatch_auxiliary_result(
            auxiliary_kind=inputs.auxiliary_kind,
            auxiliary_operation=inputs.auxiliary_operation,
            source_values=inputs.source_values,
            result_context=inputs.result_context,
            local_time_profile=inputs.local_time_profile,
            result_values=inputs.result_values,
            utc_result=inputs.utc_result,
            selection_options=inputs.selection_options,
            reader_version=inputs.reader_version,
            auxiliary_member_id=inputs.auxiliary_member_id,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48",
            refusal,
            {
                "auxiliary_kind": repr(inputs.auxiliary_kind),
                "auxiliary_operation": repr(inputs.auxiliary_operation),
                "source_values": repr(inputs.source_values),
                "result_context": repr(inputs.result_context),
                "local_time_profile": repr(inputs.local_time_profile),
                "result_values": repr(inputs.result_values),
                "utc_result": repr(inputs.utc_result),
                "selection_options": repr(inputs.selection_options),
                "reader_version": repr(inputs.reader_version),
                "auxiliary_member_id": repr(inputs.auxiliary_member_id),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B08_raw(inputs: _Inputs) -> None:
    try:
        canonical._retain_raw_source_record(
            source_record=inputs.source_record, native_profile=inputs.native_profile
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B08.raw",
            refusal,
            {
                "source_record": repr(inputs.source_record),
                "native_profile": repr(inputs.native_profile),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B08_origin(inputs: _Inputs) -> None:
    try:
        canonical._check_station_origin(
            station=inputs.station, release_origin=inputs.release_origin
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B08.origin",
            refusal,
            {
                "station": repr(inputs.station),
                "release_origin": repr(inputs.release_origin),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B23_lock(inputs: _Inputs) -> None:
    try:
        canonical._manage_cache_lock(
            lock_request=inputs.lock_request,
            lock_state=inputs.lock_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B23.lock",
            refusal,
            {
                "lock_request": repr(inputs.lock_request),
                "lock_state": repr(inputs.lock_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B23_http(inputs: _Inputs) -> None:
    try:
        canonical._request_http_resource(
            http_request=inputs.http_request, transport_options=inputs.transport_options
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B23.http",
            refusal,
            {
                "http_request": repr(inputs.http_request),
                "transport_options": repr(inputs.transport_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B35_stats(inputs: _Inputs) -> None:
    try:
        canonical._count_release_statistics(release_view=inputs.release_view)
    except NotImplementedError as refusal:
        _record_entry("B35.stats", refusal, {"release_view": repr(inputs.release_view)})
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B35_sets(inputs: _Inputs) -> None:
    try:
        canonical._order_constant_sets(
            station_sets=inputs.station_sets,
            original_recommendation=inputs.original_recommendation,
            commercial_only=inputs.commercial_only,
            include_no_constants=inputs.include_no_constants,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B35.sets",
            refusal,
            {
                "station_sets": repr(inputs.station_sets),
                "original_recommendation": repr(inputs.original_recommendation),
                "commercial_only": repr(inputs.commercial_only),
                "include_no_constants": repr(inputs.include_no_constants),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_aux(inputs: _Inputs) -> None:
    try:
        canonical._read_auxiliary_model_value(
            auxiliary_operation=inputs.auxiliary_operation,
            source_values=inputs.source_values,
            selection_options=inputs.selection_options,
            reader_version=inputs.reader_version,
            auxiliary_member_id=inputs.auxiliary_member_id,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.aux",
            refusal,
            {
                "auxiliary_operation": repr(inputs.auxiliary_operation),
                "source_values": repr(inputs.source_values),
                "selection_options": repr(inputs.selection_options),
                "reader_version": repr(inputs.reader_version),
                "auxiliary_member_id": repr(inputs.auxiliary_member_id),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_context(inputs: _Inputs) -> None:
    try:
        canonical._construct_prediction_result(
            result_values=inputs.result_values, result_context=inputs.result_context
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.context",
            refusal,
            {
                "result_values": repr(inputs.result_values),
                "result_context": repr(inputs.result_context),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_local(inputs: _Inputs) -> None:
    try:
        canonical._convert_result_to_local_time(
            utc_result=inputs.utc_result, local_time_profile=inputs.local_time_profile
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.local",
            refusal,
            {
                "utc_result": repr(inputs.utc_result),
                "local_time_profile": repr(inputs.local_time_profile),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B43_roots(inputs: _Inputs) -> None:
    try:
        canonical._find_unrounded_tide_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B43.roots",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B44_roots(inputs: _Inputs) -> None:
    try:
        canonical._find_unrounded_current_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B44.roots",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
                "current_request": repr(inputs.current_request),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_sidecar(inputs: _Inputs) -> None:
    try:
        canonical._acquire_checksum_sidecar(
            acquisition_descriptor=inputs.acquisition_descriptor,
            effective_options=inputs.effective_options,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.sidecar",
            refusal,
            {
                "acquisition_descriptor": repr(inputs.acquisition_descriptor),
                "effective_options": repr(inputs.effective_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B08_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._retain_raw_source_record(
            source_record=inputs.source_record, native_profile=inputs.native_profile
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B08.S1.A1",
            refusal,
            {
                "source_record": repr(inputs.source_record),
                "native_profile": repr(inputs.native_profile),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B08_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._check_station_origin(
            station=inputs.station, release_origin=inputs.release_origin
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B08.S1.A2",
            refusal,
            {
                "station": repr(inputs.station),
                "release_origin": repr(inputs.release_origin),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B09_S1_A3(inputs: _Inputs) -> None:
    try:
        canonical._validate_operation_arguments(
            operation=inputs.operation,
            arguments=inputs.arguments,
            member_contract=inputs.member_contract,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B09.S1.A3",
            refusal,
            {
                "operation": repr(inputs.operation),
                "arguments": repr(inputs.arguments),
                "member_contract": repr(inputs.member_contract),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B09_S1_A4(inputs: _Inputs) -> None:
    try:
        canonical._resolve_effective_options(
            explicit_options=inputs.explicit_options,
            environment=inputs.environment,
            platform_defaults=inputs.platform_defaults,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B09.S1.A4",
            refusal,
            {
                "explicit_options": repr(inputs.explicit_options),
                "environment": repr(inputs.environment),
                "platform_defaults": repr(inputs.platform_defaults),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B09_S1_A5(inputs: _Inputs) -> None:
    try:
        canonical._resolve_release_request(
            release_request=inputs.release_request,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B09.S1.A5",
            refusal,
            {
                "release_request": repr(inputs.release_request),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B09_S2_A4(inputs: _Inputs) -> None:
    try:
        canonical._bind_checksum_manifest(
            checksum_bytes=inputs.checksum_bytes,
            pointer_digests=inputs.pointer_digests,
            required_files=inputs.required_files,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B09.S2.A4",
            refusal,
            {
                "checksum_bytes": repr(inputs.checksum_bytes),
                "pointer_digests": repr(inputs.pointer_digests),
                "required_files": repr(inputs.required_files),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B09_S2_A9(inputs: _Inputs) -> None:
    try:
        canonical._decode_release_document(
            source_bytes=inputs.source_bytes,
            reader_version=inputs.reader_version,
            document_kind=inputs.document_kind,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B09.S2.A9",
            refusal,
            {
                "source_bytes": repr(inputs.source_bytes),
                "reader_version": repr(inputs.reader_version),
                "document_kind": repr(inputs.document_kind),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B09_S2_A11(inputs: _Inputs) -> None:
    try:
        canonical._validate_release_links(
            parsed_document=inputs.parsed_document, required_links=inputs.required_links
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B09.S2.A11",
            refusal,
            {
                "parsed_document": repr(inputs.parsed_document),
                "required_links": repr(inputs.required_links),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B10_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._select_cached_release(
            release_candidates=inputs.release_candidates,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B10.S1.A2",
            refusal,
            {
                "release_candidates": repr(inputs.release_candidates),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B10_S1_A5(inputs: _Inputs) -> None:
    try:
        canonical._acquire_release_files(
            load_mode=inputs.load_mode,
            cache_state=inputs.cache_state,
            acquisition_descriptor=inputs.acquisition_descriptor,
            effective_options=inputs.effective_options,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B10.S1.A5",
            refusal,
            {
                "load_mode": repr(inputs.load_mode),
                "cache_state": repr(inputs.cache_state),
                "acquisition_descriptor": repr(inputs.acquisition_descriptor),
                "effective_options": repr(inputs.effective_options),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B10_S2_A1(inputs: _Inputs) -> None:
    try:
        canonical._select_cached_release(
            release_candidates=inputs.release_candidates,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B10.S2.A1",
            refusal,
            {
                "release_candidates": repr(inputs.release_candidates),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B10_S3_A4(inputs: _Inputs) -> None:
    try:
        canonical._exchange_release_metadata(
            metadata_request=inputs.metadata_request,
            trusted_cache=inputs.trusted_cache,
            transport_options=inputs.transport_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B10.S3.A4",
            refusal,
            {
                "metadata_request": repr(inputs.metadata_request),
                "trusted_cache": repr(inputs.trusted_cache),
                "transport_options": repr(inputs.transport_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B10_S3_A6(inputs: _Inputs) -> None:
    try:
        canonical._acquire_release_files(
            load_mode=inputs.load_mode,
            cache_state=inputs.cache_state,
            acquisition_descriptor=inputs.acquisition_descriptor,
            effective_options=inputs.effective_options,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B10.S3.A6",
            refusal,
            {
                "load_mode": repr(inputs.load_mode),
                "cache_state": repr(inputs.cache_state),
                "acquisition_descriptor": repr(inputs.acquisition_descriptor),
                "effective_options": repr(inputs.effective_options),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B10_S4_A1(inputs: _Inputs) -> None:
    try:
        canonical._select_cached_release(
            release_candidates=inputs.release_candidates,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B10.S4.A1",
            refusal,
            {
                "release_candidates": repr(inputs.release_candidates),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B11_S2_A2(inputs: _Inputs) -> None:
    try:
        canonical._request_http_resource(
            http_request=inputs.http_request, transport_options=inputs.transport_options
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B11.S2.A2",
            refusal,
            {
                "http_request": repr(inputs.http_request),
                "transport_options": repr(inputs.transport_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B11_S3_A5(inputs: _Inputs) -> None:
    try:
        canonical._decode_release_document(
            source_bytes=inputs.source_bytes,
            reader_version=inputs.reader_version,
            document_kind=inputs.document_kind,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B11.S3.A5",
            refusal,
            {
                "source_bytes": repr(inputs.source_bytes),
                "reader_version": repr(inputs.reader_version),
                "document_kind": repr(inputs.document_kind),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B11_S5_A2(inputs: _Inputs) -> None:
    try:
        canonical._manage_cache_lock(
            lock_request=inputs.lock_request,
            lock_state=inputs.lock_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B11.S5.A2",
            refusal,
            {
                "lock_request": repr(inputs.lock_request),
                "lock_state": repr(inputs.lock_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B11_S5_A4(inputs: _Inputs) -> None:
    try:
        canonical._encode_cache_json(cache_document=inputs.cache_document)
    except NotImplementedError as refusal:
        _record_entry(
            "B11.S5.A4", refusal, {"cache_document": repr(inputs.cache_document)}
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B12_S1_A3(inputs: _Inputs) -> None:
    try:
        canonical._enforce_resource_lifetime(
            resource_state=inputs.resource_state, lifetime_action=inputs.lifetime_action
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B12.S1.A3",
            refusal,
            {
                "resource_state": repr(inputs.resource_state),
                "lifetime_action": repr(inputs.lifetime_action),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B12_S1_A7(inputs: _Inputs) -> None:
    try:
        canonical._exchange_release_metadata(
            metadata_request=inputs.metadata_request,
            trusted_cache=inputs.trusted_cache,
            transport_options=inputs.transport_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B12.S1.A7",
            refusal,
            {
                "metadata_request": repr(inputs.metadata_request),
                "trusted_cache": repr(inputs.trusted_cache),
                "transport_options": repr(inputs.transport_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B12_S2_A2(inputs: _Inputs) -> None:
    try:
        canonical._resolve_release_request(
            release_request=inputs.release_request,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B12.S2.A2",
            refusal,
            {
                "release_request": repr(inputs.release_request),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B13_S3_A2(inputs: _Inputs) -> None:
    try:
        canonical._update_client_release(
            client_state=inputs.client_state,
            update_request=inputs.update_request,
            clock=inputs.clock,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B13.S3.A2",
            refusal,
            {
                "client_state": repr(inputs.client_state),
                "update_request": repr(inputs.update_request),
                "clock": repr(inputs.clock),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B14_S2_A2(inputs: _Inputs) -> None:
    try:
        canonical._enforce_resource_lifetime(
            resource_state=inputs.resource_state, lifetime_action=inputs.lifetime_action
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B14.S2.A2",
            refusal,
            {
                "resource_state": repr(inputs.resource_state),
                "lifetime_action": repr(inputs.lifetime_action),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._manage_cache_lock(
            lock_request=inputs.lock_request,
            lock_state=inputs.lock_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.S1.A2",
            refusal,
            {
                "lock_request": repr(inputs.lock_request),
                "lock_state": repr(inputs.lock_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_S1_A3(inputs: _Inputs) -> None:
    try:
        canonical._select_cached_release(
            release_candidates=inputs.release_candidates,
            effective_options=inputs.effective_options,
            cache_state=inputs.cache_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.S1.A3",
            refusal,
            {
                "release_candidates": repr(inputs.release_candidates),
                "effective_options": repr(inputs.effective_options),
                "cache_state": repr(inputs.cache_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_S2_A1(inputs: _Inputs) -> None:
    try:
        canonical._acquire_checksum_sidecar(
            acquisition_descriptor=inputs.acquisition_descriptor,
            effective_options=inputs.effective_options,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.S2.A1",
            refusal,
            {
                "acquisition_descriptor": repr(inputs.acquisition_descriptor),
                "effective_options": repr(inputs.effective_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_S2_A3(inputs: _Inputs) -> None:
    try:
        canonical._bind_checksum_manifest(
            checksum_bytes=inputs.checksum_bytes,
            pointer_digests=inputs.pointer_digests,
            required_files=inputs.required_files,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.S2.A3",
            refusal,
            {
                "checksum_bytes": repr(inputs.checksum_bytes),
                "pointer_digests": repr(inputs.pointer_digests),
                "required_files": repr(inputs.required_files),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_S2_A6(inputs: _Inputs) -> None:
    try:
        canonical._request_http_resource(
            http_request=inputs.http_request, transport_options=inputs.transport_options
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.S2.A6",
            refusal,
            {
                "http_request": repr(inputs.http_request),
                "transport_options": repr(inputs.transport_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_S4_A2(inputs: _Inputs) -> None:
    try:
        canonical._merge_cache_receipt(
            locked_cache_state=inputs.locked_cache_state,
            verified_file_rows=inputs.verified_file_rows,
            release_metadata=inputs.release_metadata,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.S4.A2",
            refusal,
            {
                "locked_cache_state": repr(inputs.locked_cache_state),
                "verified_file_rows": repr(inputs.verified_file_rows),
                "release_metadata": repr(inputs.release_metadata),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_S5_A4(inputs: _Inputs) -> None:
    try:
        canonical._authenticate_station_index(
            source_files=inputs.source_files,
            supplied_index=inputs.supplied_index,
            index_presence=inputs.index_presence,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.S5.A4",
            refusal,
            {
                "source_files": repr(inputs.source_files),
                "supplied_index": repr(inputs.supplied_index),
                "index_presence": repr(inputs.index_presence),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B18_S4_A2(inputs: _Inputs) -> None:
    try:
        canonical._encode_cache_json(cache_document=inputs.cache_document)
    except NotImplementedError as refusal:
        _record_entry(
            "B18.S4.A2", refusal, {"cache_document": repr(inputs.cache_document)}
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B19_S3_A2(inputs: _Inputs) -> None:
    try:
        canonical._manage_cache_lock(
            lock_request=inputs.lock_request,
            lock_state=inputs.lock_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B19.S3.A2",
            refusal,
            {
                "lock_request": repr(inputs.lock_request),
                "lock_state": repr(inputs.lock_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B20_S2_A2(inputs: _Inputs) -> None:
    try:
        canonical._bind_checksum_manifest(
            checksum_bytes=inputs.checksum_bytes,
            pointer_digests=inputs.pointer_digests,
            required_files=inputs.required_files,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B20.S2.A2",
            refusal,
            {
                "checksum_bytes": repr(inputs.checksum_bytes),
                "pointer_digests": repr(inputs.pointer_digests),
                "required_files": repr(inputs.required_files),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B21_S2_A1(inputs: _Inputs) -> None:
    try:
        canonical._bind_checksum_manifest(
            checksum_bytes=inputs.checksum_bytes,
            pointer_digests=inputs.pointer_digests,
            required_files=inputs.required_files,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B21.S2.A1",
            refusal,
            {
                "checksum_bytes": repr(inputs.checksum_bytes),
                "pointer_digests": repr(inputs.pointer_digests),
                "required_files": repr(inputs.required_files),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B22_S4_A2(inputs: _Inputs) -> None:
    try:
        canonical._manage_cache_lock(
            lock_request=inputs.lock_request,
            lock_state=inputs.lock_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B22.S4.A2",
            refusal,
            {
                "lock_request": repr(inputs.lock_request),
                "lock_state": repr(inputs.lock_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B23_S1_A5(inputs: _Inputs) -> None:
    try:
        canonical._manage_cache_lock(
            lock_request=inputs.lock_request,
            lock_state=inputs.lock_state,
            clock=inputs.clock,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B23.S1.A5",
            refusal,
            {
                "lock_request": repr(inputs.lock_request),
                "lock_state": repr(inputs.lock_state),
                "clock": repr(inputs.clock),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B23_S1_A7(inputs: _Inputs) -> None:
    try:
        canonical._request_http_resource(
            http_request=inputs.http_request, transport_options=inputs.transport_options
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B23.S1.A7",
            refusal,
            {
                "http_request": repr(inputs.http_request),
                "transport_options": repr(inputs.transport_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B25_S4_A4(inputs: _Inputs) -> None:
    try:
        canonical._project_station_index(
            station_source_row=inputs.station_source_row,
            source_byte_span=inputs.source_byte_span,
            projection_contract=inputs.projection_contract,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B25.S4.A4",
            refusal,
            {
                "station_source_row": repr(inputs.station_source_row),
                "source_byte_span": repr(inputs.source_byte_span),
                "projection_contract": repr(inputs.projection_contract),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B25_S4_A6(inputs: _Inputs) -> None:
    try:
        canonical._encode_cache_json(cache_document=inputs.cache_document)
    except NotImplementedError as refusal:
        _record_entry(
            "B25.S4.A6", refusal, {"cache_document": repr(inputs.cache_document)}
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B27_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._enforce_resource_lifetime(
            resource_state=inputs.resource_state, lifetime_action=inputs.lifetime_action
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B27.S1.A1",
            refusal,
            {
                "resource_state": repr(inputs.resource_state),
                "lifetime_action": repr(inputs.lifetime_action),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B27_S4_A3(inputs: _Inputs) -> None:
    try:
        canonical._decode_release_document(
            source_bytes=inputs.source_bytes,
            reader_version=inputs.reader_version,
            document_kind=inputs.document_kind,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B27.S4.A3",
            refusal,
            {
                "source_bytes": repr(inputs.source_bytes),
                "reader_version": repr(inputs.reader_version),
                "document_kind": repr(inputs.document_kind),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B27_S4_A7(inputs: _Inputs) -> None:
    try:
        canonical._compare_station_source(
            index_entry=inputs.index_entry,
            station_source_row=inputs.station_source_row,
            index_presence=inputs.index_presence,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B27.S4.A7",
            refusal,
            {
                "index_entry": repr(inputs.index_entry),
                "station_source_row": repr(inputs.station_source_row),
                "index_presence": repr(inputs.index_presence),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B29_S4_A4(inputs: _Inputs) -> None:
    try:
        canonical._read_station_lazily(
            stream_reader=inputs.stream_reader,
            station_id=inputs.station_id,
            release_origin=inputs.release_origin,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B29.S4.A4",
            refusal,
            {
                "stream_reader": repr(inputs.stream_reader),
                "station_id": repr(inputs.station_id),
                "release_origin": repr(inputs.release_origin),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B29_S4_A8(inputs: _Inputs) -> None:
    try:
        canonical._materialize_typed_model(
            raw_fields=inputs.raw_fields,
            field_contract=inputs.field_contract,
            origin=inputs.origin,
            model_type=inputs.model_type,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B29.S4.A8",
            refusal,
            {
                "raw_fields": repr(inputs.raw_fields),
                "field_contract": repr(inputs.field_contract),
                "origin": repr(inputs.origin),
                "model_type": repr(inputs.model_type),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B34_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._enforce_resource_lifetime(
            resource_state=inputs.resource_state, lifetime_action=inputs.lifetime_action
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B34.S1.A1",
            refusal,
            {
                "resource_state": repr(inputs.resource_state),
                "lifetime_action": repr(inputs.lifetime_action),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B34_S2_A4(inputs: _Inputs) -> None:
    try:
        canonical._select_effective_recommendation(
            station_sets=inputs.station_sets,
            original_recommendation=inputs.original_recommendation,
            commercial_only=inputs.commercial_only,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B34.S2.A4",
            refusal,
            {
                "station_sets": repr(inputs.station_sets),
                "original_recommendation": repr(inputs.original_recommendation),
                "commercial_only": repr(inputs.commercial_only),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B34_S2_A6(inputs: _Inputs) -> None:
    try:
        canonical._resolve_reference_path(
            station_source_row=inputs.station_source_row,
            path_request=inputs.path_request,
            release_view=inputs.release_view,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B34.S2.A6",
            refusal,
            {
                "station_source_row": repr(inputs.station_source_row),
                "path_request": repr(inputs.path_request),
                "release_view": repr(inputs.release_view),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B34_S3_A3(inputs: _Inputs) -> None:
    try:
        canonical._admit_quality_path(
            candidate_path=inputs.candidate_path,
            include_flagged=inputs.include_flagged,
            include_fallback=inputs.include_fallback,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B34.S3.A3",
            refusal,
            {
                "candidate_path": repr(inputs.candidate_path),
                "include_flagged": repr(inputs.include_flagged),
                "include_fallback": repr(inputs.include_fallback),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B34_S3_A4(inputs: _Inputs) -> None:
    try:
        canonical._admit_commercial_path(
            candidate_path=inputs.candidate_path,
            commercial_only=inputs.commercial_only,
            commercial_basis=inputs.commercial_basis,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B34.S3.A4",
            refusal,
            {
                "candidate_path": repr(inputs.candidate_path),
                "commercial_only": repr(inputs.commercial_only),
                "commercial_basis": repr(inputs.commercial_basis),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B34_S3_A8(inputs: _Inputs) -> None:
    try:
        canonical._admit_historical_offset(
            own_offset=inputs.own_offset,
            reference_path=inputs.reference_path,
            historical_policy=inputs.historical_policy,
            selection_kind=inputs.selection_kind,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B34.S3.A8",
            refusal,
            {
                "own_offset": repr(inputs.own_offset),
                "reference_path": repr(inputs.reference_path),
                "historical_policy": repr(inputs.historical_policy),
                "selection_kind": repr(inputs.selection_kind),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B35_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._count_release_statistics(release_view=inputs.release_view)
    except NotImplementedError as refusal:
        _record_entry("B35.S1.A1", refusal, {"release_view": repr(inputs.release_view)})
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B35_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._order_constant_sets(
            station_sets=inputs.station_sets,
            original_recommendation=inputs.original_recommendation,
            commercial_only=inputs.commercial_only,
            include_no_constants=inputs.include_no_constants,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B35.S1.A2",
            refusal,
            {
                "station_sets": repr(inputs.station_sets),
                "original_recommendation": repr(inputs.original_recommendation),
                "commercial_only": repr(inputs.commercial_only),
                "include_no_constants": repr(inputs.include_no_constants),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B36_S7_A2(inputs: _Inputs) -> None:
    try:
        canonical._select_prediction_model(
            release_view=inputs.release_view,
            selection_options=inputs.selection_options,
            station_request=inputs.station_request,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B36.S7.A2",
            refusal,
            {
                "release_view": repr(inputs.release_view),
                "selection_options": repr(inputs.selection_options),
                "station_request": repr(inputs.station_request),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B37_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._check_station_origin(
            station=inputs.station, release_origin=inputs.release_origin
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B37.S1.A2",
            refusal,
            {
                "station": repr(inputs.station),
                "release_origin": repr(inputs.release_origin),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B37_S2_A3(inputs: _Inputs) -> None:
    try:
        canonical._select_effective_recommendation(
            station_sets=inputs.station_sets,
            original_recommendation=inputs.original_recommendation,
            commercial_only=inputs.commercial_only,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B37.S2.A3",
            refusal,
            {
                "station_sets": repr(inputs.station_sets),
                "original_recommendation": repr(inputs.original_recommendation),
                "commercial_only": repr(inputs.commercial_only),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B37_S2_A5(inputs: _Inputs) -> None:
    try:
        canonical._resolve_reference_path(
            station_source_row=inputs.station_source_row,
            path_request=inputs.path_request,
            release_view=inputs.release_view,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B37.S2.A5",
            refusal,
            {
                "station_source_row": repr(inputs.station_source_row),
                "path_request": repr(inputs.path_request),
                "release_view": repr(inputs.release_view),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B40_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._check_station_origin(
            station=inputs.station, release_origin=inputs.release_origin
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B40.S1.A2",
            refusal,
            {
                "station": repr(inputs.station),
                "release_origin": repr(inputs.release_origin),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B40_S1_A3(inputs: _Inputs) -> None:
    try:
        canonical._lookup_station_identity(
            release_view=inputs.release_view,
            identity_query=inputs.identity_query,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B40.S1.A3",
            refusal,
            {
                "release_view": repr(inputs.release_view),
                "identity_query": repr(inputs.identity_query),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B40_S2_A4(inputs: _Inputs) -> None:
    try:
        canonical._select_effective_recommendation(
            station_sets=inputs.station_sets,
            original_recommendation=inputs.original_recommendation,
            commercial_only=inputs.commercial_only,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B40.S2.A4",
            refusal,
            {
                "station_sets": repr(inputs.station_sets),
                "original_recommendation": repr(inputs.original_recommendation),
                "commercial_only": repr(inputs.commercial_only),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B42_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B42.S1.A2",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "utc_instant": repr(inputs.utc_instant),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B43_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._find_unrounded_tide_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B43.S1.A1",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B44_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._find_unrounded_current_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B44.S1.A1",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
                "current_request": repr(inputs.current_request),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B45_S2_A3(inputs: _Inputs) -> None:
    try:
        canonical._admit_historical_offset(
            own_offset=inputs.own_offset,
            reference_path=inputs.reference_path,
            historical_policy=inputs.historical_policy,
            selection_kind=inputs.selection_kind,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B45.S2.A3",
            refusal,
            {
                "own_offset": repr(inputs.own_offset),
                "reference_path": repr(inputs.reference_path),
                "historical_policy": repr(inputs.historical_policy),
                "selection_kind": repr(inputs.selection_kind),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B45_S3_A2(inputs: _Inputs) -> None:
    try:
        canonical._select_prediction_model(
            release_view=inputs.release_view,
            selection_options=inputs.selection_options,
            station_request=inputs.station_request,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B45.S3.A2",
            refusal,
            {
                "release_view": repr(inputs.release_view),
                "selection_options": repr(inputs.selection_options),
                "station_request": repr(inputs.station_request),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B45_S6_A2(inputs: _Inputs) -> None:
    try:
        canonical._find_unrounded_tide_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B45.S6.A2",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B45_S7_A3(inputs: _Inputs) -> None:
    try:
        canonical._fold_equal_tide_offset(
            own_offset=inputs.own_offset,
            reference_model=inputs.reference_model,
            prediction_instants=inputs.prediction_instants,
            requested_datum=inputs.requested_datum,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B45.S7.A3",
            refusal,
            {
                "own_offset": repr(inputs.own_offset),
                "reference_model": repr(inputs.reference_model),
                "prediction_instants": repr(inputs.prediction_instants),
                "requested_datum": repr(inputs.requested_datum),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B46_S3_A2(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_harmonic_height(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_instants=inputs.prediction_instants,
            requested_datum=inputs.requested_datum,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B46.S3.A2",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_instants": repr(inputs.prediction_instants),
                "requested_datum": repr(inputs.requested_datum),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B47_S2_A2(inputs: _Inputs) -> None:
    try:
        canonical._select_prediction_model(
            release_view=inputs.release_view,
            selection_options=inputs.selection_options,
            station_request=inputs.station_request,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B47.S2.A2",
            refusal,
            {
                "release_view": repr(inputs.release_view),
                "selection_options": repr(inputs.selection_options),
                "station_request": repr(inputs.station_request),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B47_S4_A3(inputs: _Inputs) -> None:
    try:
        canonical._find_unrounded_current_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B47.S4.A3",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "prediction_window": repr(inputs.prediction_window),
                "current_request": repr(inputs.current_request),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._read_auxiliary_model_value(
            source_values=inputs.source_values,
            selection_options=inputs.selection_options,
            auxiliary_operation=inputs.auxiliary_operation,
            reader_version=inputs.reader_version,
            auxiliary_member_id=inputs.auxiliary_member_id,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.S1.A1",
            refusal,
            {
                "source_values": repr(inputs.source_values),
                "selection_options": repr(inputs.selection_options),
                "auxiliary_operation": repr(inputs.auxiliary_operation),
                "reader_version": repr(inputs.reader_version),
                "auxiliary_member_id": repr(inputs.auxiliary_member_id),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._construct_prediction_result(
            result_values=inputs.result_values, result_context=inputs.result_context
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.S1.A2",
            refusal,
            {
                "result_values": repr(inputs.result_values),
                "result_context": repr(inputs.result_context),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_S1_A3(inputs: _Inputs) -> None:
    try:
        canonical._convert_result_to_local_time(
            utc_result=inputs.utc_result, local_time_profile=inputs.local_time_profile
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.S1.A3",
            refusal,
            {
                "utc_result": repr(inputs.utc_result),
                "local_time_profile": repr(inputs.local_time_profile),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B35_sets_S1_A1(inputs: _Inputs) -> None:
    try:
        canonical._select_effective_recommendation(
            station_sets=inputs.station_sets,
            original_recommendation=inputs.original_recommendation,
            commercial_only=inputs.commercial_only,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B35.sets.S1.A1",
            refusal,
            {
                "station_sets": repr(inputs.station_sets),
                "original_recommendation": repr(inputs.original_recommendation),
                "commercial_only": repr(inputs.commercial_only),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_aux_S2_A1(inputs: _Inputs) -> None:
    try:
        canonical._select_prediction_model(
            release_view=inputs.release_view,
            selection_options=inputs.selection_options,
            station_request=inputs.station_request,
            reader_version=inputs.reader_version,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.aux.S2.A1",
            refusal,
            {
                "release_view": repr(inputs.release_view),
                "selection_options": repr(inputs.selection_options),
                "station_request": repr(inputs.station_request),
                "reader_version": repr(inputs.reader_version),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B48_aux_S2_A2(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B48.aux.S2.A2",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "utc_instant": repr(inputs.utc_instant),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B43_roots_S1_A2(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B43.roots.S1.A2",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "utc_instant": repr(inputs.utc_instant),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B44_roots_S2_A2(inputs: _Inputs) -> None:
    try:
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B44.roots.S2.A2",
            refusal,
            {
                "selected_prediction_model": repr(inputs.selected_prediction_model),
                "utc_instant": repr(inputs.utc_instant),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_construction_B17_sidecar_S1_A3(inputs: _Inputs) -> None:
    try:
        canonical._request_http_resource(
            http_request=inputs.http_request, transport_options=inputs.transport_options
        )
    except NotImplementedError as refusal:
        _record_entry(
            "B17.sidecar.S1.A3",
            refusal,
            {
                "http_request": repr(inputs.http_request),
                "transport_options": repr(inputs.transport_options),
            },
        )
    else:
        pytest.fail("Construction stub returned a fabricated result")


def test_native_channels_preserve_absent_null_and_no_value() -> None:
    absent = types._Absent()
    null_result = types._MemberValue3(member_id="Client.last_error", value=None)
    no_value = types._SuccessfulNoValue(member_id="Client.close")
    assert absent != null_result and absent != no_value and null_result != no_value
    assert types._OMITTED is not None


def test_public_route_does_not_import_private_stubs() -> None:
    source = (ROOT / "python" / "src" / "opentideconstants" / "_client.py").read_text(
        encoding="utf-8"
    )
    assert "_canonical" not in source
    with OpenTideConstants(
        file=ROOT / "conformance" / "fixtures" / "good" / "OTC_20991231.json"
    ) as client:
        assert client.release.datestamp == "20991231"
        assert client.release.require_station("OTC-T-0001").station_id == "OTC-T-0001"
