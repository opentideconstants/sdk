"""Construction proof: candidate native entries, never runtime behavior acceptance."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, fields, is_dataclass
import json
from pathlib import Path
import sys
import pytest
from contextlib import contextmanager
import datetime as dt
import math
from types import MappingProxyType
from collections.abc import MutableMapping
from dataclasses import replace
from types import FrameType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python" / "src"))

# Candidate source-path setup intentionally precedes native imports, as in test_unit.py.
from opentideconstants import OpenTideConstants  # noqa: E402
from opentideconstants import _canonical as canonical  # noqa: E402
from opentideconstants import _canonical_types as types  # noqa: E402
from opentideconstants import _client, _models, _release, _errors, _enums  # noqa: E402
from opentideconstants._predict import _engine, _harmonic, _astro  # noqa: E402


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


def test_construction_B01(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B01", "_validate_operation_arguments"):
        canonical._validate_operation_arguments(
            operation=inputs.operation,
            arguments=inputs.arguments,
            member_contract=inputs.member_contract,
        )


def test_construction_B02(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B02", "_resolve_effective_options"):
        canonical._resolve_effective_options(
            explicit_options=inputs.explicit_options,
            environment=inputs.environment,
            platform_defaults=inputs.platform_defaults,
        )


def test_construction_B03(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B03", "_select_canonical_error"):
        canonical._select_canonical_error(
            operation=inputs.operation,
            ordered_failures=inputs.ordered_failures,
            cause=inputs.cause,
        )


def test_construction_B04(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B04", "_translate_native_binding"):
        canonical._translate_native_binding(
            canonical_result=inputs.canonical_result,
            canonical_error=inputs.canonical_error,
            native_profile=inputs.native_profile,
        )


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


def test_construction_B07(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B07", "_materialize_typed_model"):
        canonical._materialize_typed_model(
            raw_fields=inputs.raw_fields,
            field_contract=inputs.field_contract,
            origin=inputs.origin,
            model_type=inputs.model_type,
        )


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


def test_construction_B24(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B24", "_project_station_index"):
        canonical._project_station_index(
            station_source_row=inputs.station_source_row,
            source_byte_span=inputs.source_byte_span,
            projection_contract=inputs.projection_contract,
        )


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


def test_construction_B28(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B28", "_encode_cache_json"):
        canonical._encode_cache_json(cache_document=inputs.cache_document)


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


def test_construction_B39(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B39", "_parse_prediction_window"):
        canonical._parse_prediction_window(
            time_inputs=inputs.time_inputs,
            window_inputs=inputs.window_inputs,
            step=inputs.step,
            local_time_profile=inputs.local_time_profile,
        )


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


def test_construction_B41(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B41", "_evaluate_astronomy"):
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )


def test_construction_B42(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B42", "_evaluate_harmonic_height"):
        canonical._evaluate_harmonic_height(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_instants=inputs.prediction_instants,
            requested_datum=inputs.requested_datum,
        )


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


def test_construction_B08_raw(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B08.raw", "_retain_raw_source_record"):
        canonical._retain_raw_source_record(
            source_record=inputs.source_record, native_profile=inputs.native_profile
        )


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


def test_construction_B43_roots(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B43.roots", "_find_unrounded_tide_events"):
        canonical._find_unrounded_tide_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
        )


def test_construction_B44_roots(m1_current_inputs: _Inputs) -> None:
    inputs = m1_current_inputs
    with _observe_reused_entry("B44.roots", "_find_unrounded_current_events"):
        canonical._find_unrounded_current_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
        )


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


def test_construction_B08_S1_A1(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B08.S1.A1", "_retain_raw_source_record"):
        canonical._retain_raw_source_record(
            source_record=inputs.source_record, native_profile=inputs.native_profile
        )


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


def test_construction_B09_S1_A3(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B09.S1.A3", "_validate_operation_arguments"):
        canonical._validate_operation_arguments(
            operation=inputs.operation,
            arguments=inputs.arguments,
            member_contract=inputs.member_contract,
        )


def test_construction_B09_S1_A4(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B09.S1.A4", "_resolve_effective_options"):
        canonical._resolve_effective_options(
            explicit_options=inputs.explicit_options,
            environment=inputs.environment,
            platform_defaults=inputs.platform_defaults,
        )


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


def test_construction_B11_S5_A4(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B11.S5.A4", "_encode_cache_json"):
        canonical._encode_cache_json(cache_document=inputs.cache_document)


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


def test_construction_B18_S4_A2(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B18.S4.A2", "_encode_cache_json"):
        canonical._encode_cache_json(cache_document=inputs.cache_document)


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


def test_construction_B25_S4_A4(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B25.S4.A4", "_project_station_index"):
        canonical._project_station_index(
            station_source_row=inputs.station_source_row,
            source_byte_span=inputs.source_byte_span,
            projection_contract=inputs.projection_contract,
        )


def test_construction_B25_S4_A6(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B25.S4.A6", "_encode_cache_json"):
        canonical._encode_cache_json(cache_document=inputs.cache_document)


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


def test_construction_B29_S4_A8(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B29.S4.A8", "_materialize_typed_model"):
        canonical._materialize_typed_model(
            raw_fields=inputs.raw_fields,
            field_contract=inputs.field_contract,
            origin=inputs.origin,
            model_type=inputs.model_type,
        )


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


def test_construction_B42_S1_A2(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B42.S1.A2", "_evaluate_astronomy"):
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )


def test_construction_B43_S1_A1(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B43.S1.A1", "_find_unrounded_tide_events"):
        canonical._find_unrounded_tide_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
        )


def test_construction_B44_S1_A1(m1_current_inputs: _Inputs) -> None:
    inputs = m1_current_inputs
    with _observe_reused_entry("B44.S1.A1", "_find_unrounded_current_events"):
        canonical._find_unrounded_current_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
        )


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


def test_construction_B45_S6_A2(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B45.S6.A2", "_find_unrounded_tide_events"):
        canonical._find_unrounded_tide_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
        )


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


def test_construction_B46_S3_A2(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B46.S3.A2", "_evaluate_harmonic_height"):
        canonical._evaluate_harmonic_height(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_instants=inputs.prediction_instants,
            requested_datum=inputs.requested_datum,
        )


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


def test_construction_B47_S4_A3(m1_current_inputs: _Inputs) -> None:
    inputs = m1_current_inputs
    with _observe_reused_entry("B47.S4.A3", "_find_unrounded_current_events"):
        canonical._find_unrounded_current_events(
            selected_prediction_model=inputs.selected_prediction_model,
            prediction_window=inputs.prediction_window,
            current_request=inputs.current_request,
        )


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


def test_construction_B48_aux_S2_A2(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B48.aux.S2.A2", "_evaluate_astronomy"):
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )


def test_construction_B43_roots_S1_A2(m1_inputs: _Inputs) -> None:
    inputs = m1_inputs
    with _observe_reused_entry("B43.roots.S1.A2", "_evaluate_astronomy"):
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )


def test_construction_B44_roots_S2_A2(m1_current_inputs: _Inputs) -> None:
    inputs = m1_current_inputs
    with _observe_reused_entry("B44.roots.S2.A2", "_evaluate_astronomy"):
        canonical._evaluate_astronomy(
            selected_prediction_model=inputs.selected_prediction_model,
            utc_instant=inputs.utc_instant,
        )


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


# M1 authentic body witnesses. These inputs are bound by the accepted CORPUS.
@dataclass(frozen=True, slots=True)
class _NativeModel(types._PredictionModel):
    native_sum: _harmonic.Sum
    native_table: _astro.AstroTable
    native_context: _engine._Context


@dataclass(frozen=True, slots=True)
class _NativeFailure(types._CanonicalError):
    native_error: _errors.OpenTideConstantsError


class _StationContracts(tuple[types._FieldContract, ...]):
    conventions: Mapping[str, _models.Convention]
    licences: Mapping[str, _models.Licence]
    kind: _enums.Kind | None
    recommendation: str | None
    rows: tuple[_models.Validation, ...]
    convention: _models.Convention
    licence: _models.Licence

    def __new__(cls, release: _release.Release, station: _models.Station):
        value = super().__new__(
            cls, (types._FieldContract("Station.station_id", "str", False, True),)
        )
        value.conventions = {c.convention_id: c for c in release.conventions}
        value.licences = {lic.licence_id: lic for lic in release.licences}
        value.kind = station.kind
        value.recommendation = (
            station.recommended_set.set_id if station.recommended_set else None
        )
        assert station.recommended_set is not None
        value.rows = station.validation
        value.convention = station.recommended_set.convention
        value.licence = station.recommended_set.licence
        return value


def _open_arguments(*, offline: bool = False) -> types._Arguments0:
    return types._Arguments0(
        member_id="Client.open",
        release="latest",
        file=str(ROOT / "conformance/fixtures/good/OTC_20991231.2.jsonl"),
        cache_dir=None,
        offline=offline,
        mode=_enums.Mode.EAGER,
        base_url=_client.DEFAULT_BASE_URL,
        timeout=None,
        proxy=None,
        ca_file=None,
        user_agent=None,
        on_network_error=_enums.OnNetworkError.USE_CACHE,
        auto_update=False,
        update_interval=86400.0,
        logger=None,
        verify_on_open=False,
        commercial_only=False,
        commercial_basis="strict",
        historical_offsets_policy="fallback",
    )


def _source_station(path: Path, station_id: str) -> Mapping[str, types._JsonValue]:
    document: types._JsonValue = json.loads(path.read_bytes())
    assert isinstance(document, Mapping)
    rows = document["stations"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, Mapping)
        if row.get("station_id") == station_id:
            return row
    raise AssertionError("Authentic source station absent")


def _native_model(
    release: _release.Release, station_id: str, quantity: str
) -> _NativeModel:
    context = _engine._context(
        release,
        station_id,
        quantity,
        None,
        datum="mean_level" if quantity == "water_level" else None,
    )
    assert isinstance(context.total, _harmonic.Sum)
    assert isinstance(context.table, _astro.AstroTable)
    return _NativeModel(
        station=context.station,
        release_view=release,
        constant_set=context.constants,
        convention=context.constants.convention,
        astro_table=context.table._raw,
        required_constituents=tuple(context.constants.raw.get("constituents") or ()),
        reference_bin=context.reference_bin,
        mean_term=context.total.mean,
        datum_source=context.constants.raw.get("datum"),
        native_sum=context.total,
        native_table=context.table,
        native_context=context,
    )


def _actual_argument_failure() -> _NativeFailure:
    args = _open_arguments(offline=True)
    try:
        OpenTideConstants(file=args.file, offline=True)
    except _errors.InvalidArgumentError as error:
        cause = error.__cause__
        assert cause is None or isinstance(cause, Exception)
        return _NativeFailure("invalid_argument", {"message": str(error)}, cause, error)
    raise AssertionError("Original native incompatible arguments did not fail")


@pytest.fixture(scope="session")
def m1_inputs(inputs: _Inputs) -> Iterator[_Inputs]:
    good = ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    with (
        OpenTideConstants(file=good) as client,
        OpenTideConstants(
            file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
        ) as prediction,
    ):
        station = client.release.require_station("OTC-T-0001")
        raw = _source_station(good, station.station_id)
        offset = 0
        for line in (
            (ROOT / "conformance/fixtures/good/OTC_20991231.2.jsonl")
            .read_bytes()
            .splitlines(keepends=True)
        ):
            row = json.loads(line)
            if row.get("station_id") == station.station_id:
                break
            offset += len(line)
        else:
            raise AssertionError("Authenticated station line absent")
        args = _open_arguments()
        start = dt.datetime(2010, 3, 10, 11, 22, 50, tzinfo=dt.timezone.utc)
        stop = dt.datetime(2010, 3, 10, 18, 5, 38, tzinfo=dt.timezone.utc)
        window = types._Arguments16(
            "Release.extremes", "OTC-P-0001", start, stop, None, None, None
        )
        model = _native_model(prediction.release, "OTC-P-0001", "water_level")
        golden = json.loads(
            (ROOT / "conformance/canonical/cache-golden.json").read_bytes()
        )
        document = next(
            c["input"]
            for c in golden["cases"]
            if "input" in c and isinstance(c["input"], dict)
        )
        yield replace(
            inputs,
            operation="open",
            arguments=args,
            member_contract=args,
            explicit_options=types._EffectiveOptions(offline=False),
            environment={"OPENTIDECONSTANTS_OFFLINE": "On"},
            platform_defaults=types._EffectiveOptions(
                base_url=_client.DEFAULT_BASE_URL, cache_dir=str(_client.default_root())
            ),
            ordered_failures=(_actual_argument_failure(),),
            canonical_result=types._MemberValue0("Client.open", client),
            canonical_error=types._Absent(),
            raw_fields=raw,
            source_record=raw,
            field_contract=_StationContracts(client.release, station),
            origin=station._origin,
            model_type="Station",
            station_source_row=row,
            source_byte_span=types._SourceByteSpan(offset, len(line)),
            cache_document=document,
            time_inputs=window,
            window_inputs=window,
            step=types._OMITTED,
            selected_prediction_model=model,
            prediction_instants=(float(_astro.instant(start)),),
            requested_datum="mean_level",
            utc_instant=float(_astro.instant(start)),
            prediction_window=types._PredictionWindow(
                float(_astro.instant(start)), float(_astro.instant(stop)), None, None
            ),
        )


@pytest.fixture(scope="session")
def m1_current_inputs(m1_inputs: _Inputs) -> Iterator[_Inputs]:
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    ) as client:
        start = dt.datetime(2010, 3, 1, tzinfo=dt.timezone.utc)
        stop = dt.datetime(2010, 3, 3, tzinfo=dt.timezone.utc)
        request = types._Arguments18(
            "Release.current_events", "OTC-P-0016", start, stop, None, None
        )
        yield replace(
            m1_inputs,
            selected_prediction_model=_native_model(
                client.release, "OTC-P-0016", "current"
            ),
            prediction_window=types._PredictionWindow(
                float(_astro.instant(start)), float(_astro.instant(stop)), None, None
            ),
            current_request=request,
        )


@contextmanager
def _observe_reused_entry(identifier: str, name: str) -> Iterator[None]:
    snapshots = []
    old = sys.getprofile()

    def capture(frame: FrameType, event: str, value):
        if (
            event == "return"
            and frame.f_code.co_name == name
            and Path(frame.f_code.co_filename).resolve()
            == Path(canonical.__file__).resolve()
        ):
            arguments = {
                arg: repr(frame.f_locals[arg])
                for arg in frame.f_code.co_varnames[
                    : frame.f_code.co_argcount + frame.f_code.co_kwonlyargcount
                ]
            }
            source = Path(frame.f_code.co_filename).resolve()
            lines = source.read_text().splitlines()
            first = last = frame.f_code.co_firstlineno - 1
            while not lines[last].endswith(":"):
                last += 1
            snapshots.append(
                {
                    "id": identifier,
                    "native_entry": "opentideconstants._canonical." + name,
                    "signature": "\n".join(lines[first : last + 1]),
                    "arguments": arguments,
                    "result": repr(value),
                    "logical_result": _observed_logical_result(value),
                    "result_member_id": (
                        frame.f_locals["canonical_result"].member_id
                        if name == "_translate_native_binding"
                        else None
                    ),
                    "module": str(source),
                    "line": first + 1,
                    "cached_module": canonical.__cached__,
                    "classification": "reused_callable",
                    "cleanup": "call-bounded native strong references; returned immutable values remain fixture-owned",
                }
            )

    try:
        sys.setprofile(capture)
        yield
    finally:
        sys.setprofile(old)
    assert len(snapshots) == 1, "Required genuine candidate leaf return must occur once"
    with (ROOT / "python/dist/canonical-shape/invocations.jsonl").open(
        "a", encoding="utf-8"
    ) as output:
        output.write(json.dumps(snapshots[0], sort_keys=True) + "\n")


def _observed_logical_result(value):
    """Project actual native return values for the invocation observation."""
    if isinstance(value, OpenTideConstants):
        return {"release": value.release.datestamp, "loaded_from": value.loaded_from}
    if isinstance(value, _models.Station):
        return _observed_logical_result(value.raw)
    if isinstance(value, types._PredictionWindow):
        return {"start": value.start, "stop": value.stop, "step": value.step}
    if isinstance(value, types._CanonicalError):
        return {
            "code": value.code,
            "structured_fields": _observed_logical_result(value.structured_fields),
            "cause": None if value.cause is None else repr(value.cause),
        }
    if isinstance(value, Mapping):
        return {key: _observed_logical_result(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, bytes)):
        return [_observed_logical_result(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _observed_logical_result(getattr(value, field.name))
            for field in fields(value)
            if not isinstance(getattr(value, field.name), types._Omitted)
        }
    if isinstance(value, (Path, dt.datetime)):
        return str(value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise AssertionError(f"Unprojected actual native return {type(value).__name__}")


def test_m1_B01_argument_order() -> None:
    args = _open_arguments(offline=True)
    with pytest.raises(_errors.InvalidArgumentError, match="file cannot be combined"):
        canonical._validate_operation_arguments(
            operation="open", arguments=args, member_contract=args
        )


@pytest.mark.parametrize("record_index", range(28), ids=lambda i: f"Arguments{i}")
def test_m1_B01_selected_argument_records(record_index: int, tmp_path: Path) -> None:
    with (
        OpenTideConstants(
            file=ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
        ) as client,
        OpenTideConstants(
            file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
        ) as predictions,
    ):
        release = client.release
        station = release.require_station("OTC-T-0001")
        constants = station.recommended_set
        assert constants is not None
        table = predictions.release.astro_table()
        assert table is not None
        start = dt.datetime(2010, 3, 1, tzinfo=dt.timezone.utc)
        stop = dt.datetime(2010, 3, 2, tzinfo=dt.timezone.utc)
        omitted = types._OMITTED
        cases: tuple[tuple[types._COperation, types._CArguments], ...] = (
            ("open", _open_arguments()),
            ("close", types._Arguments1("Client.close")),
            (
                "download",
                types._Arguments2(
                    "Client.download",
                    release.datestamp,
                    str(tmp_path / "download"),
                    (_enums.Format.JSONL,),
                    False,
                ),
            ),
            ("prune", types._Arguments3("Client.prune", 3)),
            (
                "convention",
                types._Arguments4(
                    "Release.convention", constants.convention.convention_id
                ),
            ),
            (
                "licence",
                types._Arguments5("Release.licence", constants.licence.licence_id),
            ),
            ("station", types._Arguments6("Release.station", station.station_id)),
            (
                "station_by_alias",
                types._Arguments7(
                    "Release.station_by_alias",
                    _enums.AliasSystem.NOAA,
                    station.aliases["noaa"][0],
                ),
            ),
            (
                "stations",
                types._Arguments8(
                    "Release.stations", None, None, None, None, None, False, False
                ),
            ),
            (
                "search",
                types._Arguments9(
                    "Release.search",
                    station.name,
                    1,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    False,
                    False,
                ),
            ),
            (
                "near",
                types._Arguments10(
                    "Release.near",
                    station.lat,
                    station.lon,
                    1.0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    False,
                    False,
                ),
            ),
            (
                "nearest",
                types._Arguments11(
                    "Release.nearest",
                    station.lat,
                    station.lon,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    False,
                    False,
                ),
            ),
            (
                "reference_station",
                types._Arguments12("Release.reference_station", station),
            ),
            ("attribution", types._Arguments13("Release.attribution", (station,))),
            (
                "heights",
                types._Arguments14(
                    "Release.heights", "OTC-P-0001", start, stop, 600, None, None, None
                ),
            ),
            (
                "heights_at",
                types._Arguments15(
                    "Release.heights_at", "OTC-P-0001", (start, stop), None, None, None
                ),
            ),
            (
                "extremes",
                types._Arguments16(
                    "Release.extremes", "OTC-P-0001", start, stop, None, None, None
                ),
            ),
            (
                "currents",
                types._Arguments17(
                    "Release.currents", "OTC-P-0016", start, stop, 600, None, None
                ),
            ),
            (
                "current_events",
                types._Arguments18(
                    "Release.current_events", "OTC-P-0016", start, stop, None, None
                ),
            ),
            ("datums", types._Arguments19("Release.datums", "OTC-P-0001", None, False)),
            ("ranges", types._Arguments20("Release.ranges", "OTC-P-0001", None)),
            ("astro_table", types._Arguments21("Release.astro_table", omitted)),
            ("constant_sets", types._Arguments22("Station.constant_sets", False)),
            (
                "constant_set",
                types._Arguments23("Station.constant_set", constants.set_id),
            ),
            (
                "constituent",
                types._Arguments24(
                    "ConstantSet.constituent", constants.constituents[0].name
                ),
            ),
            (
                "equilibrium_argument",
                types._Arguments25("AstroTable.equilibrium_argument", "M2", start),
            ),
            (
                "equilibrium_for_year",
                types._Arguments26("AstroTable.equilibrium_for_year", "M2", start.year),
            ),
            ("to_local", types._Arguments27("HeightSeries.to_local", "UTC")),
        )
        operation, arguments = cases[record_index]
        contract: types._CMemberContract = arguments
        if isinstance(arguments, types._Arguments26):
            contract = types._AstroMemberContract(arguments, table)
        elif isinstance(arguments, types._Arguments13):
            release.attribution((station,))
            contract = types._B01ReleaseContract(
                arguments, release, attribution_origin_failures=(None,)
            )
        result = canonical._validate_operation_arguments(
            operation=operation, arguments=arguments, member_contract=contract
        )
        assert result == arguments
        assert not (tmp_path / "download").exists()
        assert release.require_station(station.station_id) is station


def test_m1_B01_native_constructor_preserves_policy_assignment_order() -> None:
    class NativeClient(OpenTideConstants):
        captured: "NativeClient | None" = None

        def __new__(cls, **kwargs):
            value = super().__new__(cls)
            cls.captured = value
            return value

    with pytest.raises(
        _errors.InvalidArgumentError, match="timeout must be a positive finite number"
    ):
        NativeClient(
            file=ROOT / "conformance/fixtures/good/OTC_20991231.2.json",
            timeout=-1,
            historical_offsets_policy="exclude",
        )
    assert NativeClient.captured is not None
    assert NativeClient.captured._historical_offsets_policy == "exclude"


def test_m1_B02_offline_override() -> None:
    result = canonical._resolve_effective_options(
        explicit_options=types._EffectiveOptions(offline=False),
        environment={"OPENTIDECONSTANTS_OFFLINE": "On"},
        platform_defaults=types._EffectiveOptions(
            base_url=_client.DEFAULT_BASE_URL, cache_dir=str(_client.default_root())
        ),
    )
    assert result.offline is True
    assert result.base_url == _client.DEFAULT_BASE_URL


def test_m1_B02_native_cache_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    platform = str(_client.default_root())
    selected = tmp_path / "native-cache"
    monkeypatch.setenv("OPENTIDECONSTANTS_CACHE_DIR", str(selected))
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    ) as client:
        result = canonical._resolve_effective_options(
            explicit_options=types._EffectiveOptions(),
            environment={"OPENTIDECONSTANTS_CACHE_DIR": str(selected)},
            platform_defaults=types._EffectiveOptions(cache_dir=platform),
        )
        assert result.cache_dir == str(client._cache.root) == str(selected)


def test_m1_B02_explicit_cache_precedes_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit = tmp_path / "explicit"
    environment = tmp_path / "environment"
    platform = str(_client.default_root())
    monkeypatch.setenv("OPENTIDECONSTANTS_CACHE_DIR", str(environment))
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/good/OTC_20991231.2.json",
        cache_dir=explicit,
    ) as client:
        result = canonical._resolve_effective_options(
            explicit_options=types._EffectiveOptions(cache_dir=str(explicit)),
            environment={"OPENTIDECONSTANTS_CACHE_DIR": str(environment)},
            platform_defaults=types._EffectiveOptions(cache_dir=platform),
        )
        assert result.cache_dir == str(client._cache.root) == str(explicit)
        assert not environment.exists()


def test_m1_B03_preserves_native_failure() -> None:
    failure = _actual_argument_failure()
    result = canonical._select_canonical_error(
        operation="open", ordered_failures=(failure,), cause=failure.cause
    )
    assert result is failure


def test_m1_B04_native_return() -> None:
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    ) as client:
        result = canonical._translate_native_binding(
            canonical_result=types._MemberValue0(member_id="Client.open", value=client),
            canonical_error=types._Absent(),
            native_profile="python",
        )
        assert result is client


def test_m1_B07_station_model() -> None:
    path = ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    source = _source_station(path, "OTC-T-0001")
    with OpenTideConstants(file=path) as client:
        station = client.release.require_station("OTC-T-0001")
        result = canonical._materialize_typed_model(
            raw_fields=source,
            field_contract=_StationContracts(client.release, station),
            origin=station._origin,
            model_type="Station",
        )
        assert isinstance(result, _models.Station)
        assert result.raw == station.raw and result.aliases == station.aliases
        assert result._origin is station._origin


def _source_fields(
    source: types._JsonValue, path: tuple[str | int, ...]
) -> Mapping[str, types._JsonValue]:
    for component in path:
        if isinstance(component, str):
            assert isinstance(source, Mapping)
            source = source[component]
        else:
            assert isinstance(source, (list, tuple))
            source = source[component]
    assert isinstance(source, Mapping)
    return source


@pytest.mark.parametrize(
    ("model_type", "path", "parser"),
    [
        (
            "Constituent",
            ("constant_sets", 0, "constituents", 0),
            _models.Constituent._parse,
        ),
        ("Provenance", ("constant_sets", 0, "provenance"), _models.Provenance._parse),
        (
            "ProvenanceBuild",
            ("constant_sets", 0, "provenance", "build"),
            _models.ProvenanceBuild._parse,
        ),
        ("TimeBase", ("constant_sets", 1, "time_base"), _models.TimeBase._parse),
        ("QcFlag", ("constant_sets", 1, "qc_flags", 0), _models.QcFlag._parse),
        (
            "DroppedConstituent",
            ("constant_sets", 1, "dropped_constituents", 0),
            _models.DroppedConstituent._parse,
        ),
        ("Validation", ("validation", 0), _models.Validation._parse),
    ],
)
def test_m1_B07_existing_field_parsers(
    model_type: types._CModelType,
    path: tuple[str | int, ...],
    parser: Callable[[Mapping[str, types._JsonValue]], types._CTypedModel | None],
) -> None:
    fixture = ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    source = _source_fields(_source_station(fixture, "OTC-T-0001"), path)
    expected = parser(source)
    assert expected is not None
    with OpenTideConstants(file=fixture) as client:
        station = client.release.require_station("OTC-T-0001")
        result = canonical._materialize_typed_model(
            raw_fields=source,
            field_contract=_StationContracts(client.release, station),
            origin=station._origin,
            model_type=model_type,
        )
        assert type(result) is type(expected)
        assert repr(result) == repr(expected)
        if isinstance(expected, (_models.Constituent, _models.Provenance)):
            assert isinstance(result, (_models.Constituent, _models.Provenance))
            assert result.raw == expected.raw


@pytest.mark.parametrize(
    ("model_type", "field", "parser"),
    [
        ("Convention", "conventions", _models.Convention._parse),
        ("Licence", "licences", _models.Licence._parse),
    ],
)
def test_m1_B07_existing_reference_parsers(
    model_type: types._CModelType,
    field: str,
    parser: Callable[[Mapping[str, types._JsonValue]], types._CTypedModel],
) -> None:
    fixture = ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    document: types._JsonValue = json.loads(fixture.read_bytes())
    source = _source_fields(document, (field, 0))
    expected = parser(source)
    with OpenTideConstants(file=fixture) as client:
        station = client.release.require_station("OTC-T-0001")
        result = canonical._materialize_typed_model(
            raw_fields=source,
            field_contract=_StationContracts(client.release, station),
            origin=station._origin,
            model_type=model_type,
        )
        assert isinstance(expected, (_models.Convention, _models.Licence))
        assert isinstance(result, (_models.Convention, _models.Licence))
        assert result == expected and result.raw == source


@pytest.mark.parametrize("model_type", ["ConstantSet", "RecordSpan", "Datum"])
def test_m1_B07_existing_row_constructors(model_type: types._CModelType) -> None:
    fixture = ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    raw = _source_station(fixture, "OTC-T-0001")
    with OpenTideConstants(file=fixture) as client:
        station = client.release.require_station("OTC-T-0001")
        constants = station.recommended_set
        assert constants is not None
        if model_type == "ConstantSet":
            source = _source_fields(raw, ("constant_sets", 0))
            expected = constants
        elif model_type == "RecordSpan":
            source = _source_fields(raw, ("constant_sets", 0, "record_span"))
            expected = constants.record_span
        else:
            source = _source_fields(raw, ("constant_sets", 0, "datum"))
            expected = constants.datum
        assert expected is not None
        result = canonical._materialize_typed_model(
            raw_fields=source,
            field_contract=_StationContracts(client.release, station),
            origin=station._origin,
            model_type=model_type,
        )
        assert type(result) is type(expected) and repr(result) == repr(expected)
        if isinstance(expected, _models.ConstantSet):
            assert isinstance(result, _models.ConstantSet)
            assert result.raw == expected.raw
            assert (
                result.convention is expected.convention
                and result.licence is expected.licence
            )
            assert tuple(repr(c) for c in result.constituents) == tuple(
                repr(c) for c in expected.constituents
            )
        elif isinstance(expected, _models.Datum):
            assert isinstance(result, _models.Datum)
            assert result.named == expected.named


@pytest.mark.parametrize(
    ("model_type", "station_id", "path", "parser"),
    [
        ("Tombstone", "OTC-T-0005", (), _models.Tombstone._parse),
        (
            "SubordinateOffsets",
            "OTC-T-0003",
            ("subordinate_offsets",),
            _models.SubordinateOffsets._parse,
        ),
    ],
)
def test_m1_B07_existing_station_annotations(
    model_type: types._CModelType,
    station_id: str,
    path: tuple[str | int, ...],
    parser: Callable[[Mapping[str, types._JsonValue]], types._CTypedModel],
) -> None:
    fixture = ROOT / "conformance/fixtures/good/OTC_20991231.2.json"
    source = _source_fields(_source_station(fixture, station_id), path)
    expected = parser(source)
    with OpenTideConstants(file=fixture) as client:
        station = client.release.require_station("OTC-T-0001")
        result = canonical._materialize_typed_model(
            raw_fields=source,
            field_contract=_StationContracts(client.release, station),
            origin=station._origin,
            model_type=model_type,
        )
        assert type(result) is type(expected) and repr(result) == repr(expected)
        if isinstance(expected, _models.Tombstone):
            assert isinstance(result, _models.Tombstone)
            assert result.raw == expected.raw


def test_m1_B07_existing_astro_constructor() -> None:
    fixture = ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    with OpenTideConstants(file=fixture) as client:
        model = _native_model(client.release, "OTC-P-0001", "water_level")
        assert isinstance(model.astro_table, Mapping)
        result = canonical._materialize_typed_model(
            raw_fields=model.astro_table,
            field_contract=(),
            origin=model.station._origin,
            model_type="AstroTable",
        )
        assert isinstance(result, _astro.AstroTable)
        assert result._raw == model.native_table._raw
        assert result.valid_range == model.native_table.valid_range
        assert result.equilibrium_for_year(
            "M2", 2000
        ) == model.native_table.equilibrium_for_year("M2", 2000)


def test_m1_B08_raw_source() -> None:
    source = _source_station(
        ROOT / "conformance/fixtures/good/OTC_20991231.2.json", "OTC-T-0001"
    )
    result = canonical._retain_raw_source_record(
        source_record=source, native_profile="python"
    )
    assert result == _models.freeze(source)
    assert isinstance(result, MappingProxyType)
    assert not isinstance(result, MutableMapping)


def test_m1_B24_original_span() -> None:
    path = ROOT / "conformance/fixtures/good/OTC_20991231.2.jsonl"
    offset = 0
    for line in path.read_bytes().splitlines(keepends=True):
        row = json.loads(line)
        if row.get("station_id") == "OTC-T-0001":
            break
        offset += len(line)
    else:
        raise AssertionError("Actual JSONL row absent")
    contract = types._ProjectionContract(
        "existing primitive contracts",
        "existing models",
        "source nested values",
        "existing projection",
        "source fallback",
    )
    result = canonical._project_station_index(
        station_source_row=row,
        source_byte_span=types._SourceByteSpan(offset, len(line)),
        projection_contract=contract,
    )
    assert result == _release._entry(row, offset, len(line))


def test_m1_B28_existing_golden() -> None:
    golden = json.loads((ROOT / "conformance/canonical/cache-golden.json").read_bytes())
    case = next(
        c for c in golden["cases"] if "input" in c and isinstance(c["input"], dict)
    )
    result = canonical._encode_cache_json(cache_document=case["input"])
    assert result == case["expected"].encode("utf-8")


def test_m1_B39_no_event_step() -> None:
    instant = dt.datetime(2031, 1, 1, tzinfo=dt.timezone.utc)
    args = types._Arguments16(
        "Release.extremes", "OTC-P-0001", instant, instant, None, None, None
    )
    result = canonical._parse_prediction_window(
        time_inputs=args,
        window_inputs=args,
        step=types._OMITTED,
        local_time_profile=types._LocalTimeProfile(),
    )
    assert isinstance(result, types._PredictionWindow)
    assert result.start == result.stop == _astro.instant(instant)
    assert result.step is None and result.instants is None


@pytest.mark.parametrize(
    "times", [(), (dt.datetime(2010, 3, 1, tzinfo=dt.timezone.utc),) * 2]
)
def test_m1_B39_instants_have_no_window(times: tuple[dt.datetime, ...]) -> None:
    args = types._Arguments15(
        "Release.heights_at", "OTC-P-0001", times, None, None, None
    )
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    ) as client:
        native = client.release.heights_at("OTC-P-0001", times)
        result = canonical._parse_prediction_window(
            time_inputs=args,
            window_inputs=args,
            step=types._OMITTED,
            local_time_profile=types._LocalTimeProfile(),
        )
        assert result.instants == tuple(
            float(_astro.instant(point.time)) for point in native.items
        )
        assert not hasattr(result, "start") and not hasattr(result, "stop")


def test_m1_B41_native_year_terms() -> None:
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    ) as client:
        model = _native_model(client.release, "OTC-P-0001", "water_level")
        at = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
        result = canonical._evaluate_astronomy(
            selected_prediction_model=model, utc_instant=float(_astro.instant(at))
        )
        assert result.utc_year == 2000 and result.epoch_hours == 0.0
        assert result.constituent_terms == tuple(model.native_sum._year(2000)[1])
        assert model.native_table.equilibrium_argument("M2", at) == 120.0
        assert model.native_table.node_factor("M2", at) == 1.0


def test_m1_B42_pinned_height_values(tmp_path: Path) -> None:
    vectors = json.loads((ROOT / "conformance/vectors/1.0/vectors.json").read_bytes())
    vector = next(
        v for v in vectors["vectors"] if v["id"] == "OTC-V-NOAA-1820000/heights"
    )
    instants = tuple(
        float(_astro.instant(dt.datetime.fromisoformat(s.replace("Z", "+00:00"))))
        for s in vector["args"]["times"]
    )
    native_file = tmp_path / "OTC_20261011.json"
    native_file.write_bytes(
        (ROOT / "conformance/vectors/1.0/vectors-release.json").read_bytes()
    )
    with OpenTideConstants(file=native_file) as client:
        model = _native_model(
            client.release, vector["args"]["station_id"], "water_level"
        )
        result = canonical._evaluate_harmonic_height(
            selected_prediction_model=model,
            prediction_instants=instants,
            requested_datum=vector["args"].get("datum", "mean_level"),
        )
        expected = vector["expect"]["prediction"]["items"]
        assert len(result) == len(expected)
        for actual, wanted in zip(result, expected):
            assert abs(actual - wanted["height_m"]) <= vectors["tolerances"]["height_m"]


def _prefilter_native_phase(
    total: _harmonic.Sum, start: float, stop: float, *, slack: bool = False
):
    observed = []
    old = sys.getprofile()

    def capture(frame: FrameType, event: str, result):
        if (
            event == "return"
            and frame.f_code.co_name in ("events", "_unrounded_events")
            and "kept" in frame.f_locals
        ):
            observed.append(tuple(frame.f_locals["kept"]))

    try:
        sys.setprofile(capture)
        _harmonic.events(total, start, stop, slack=slack)
    finally:
        sys.setprofile(old)
    assert len(observed) == 1
    return observed[0]


def test_m1_B43_actual_excluded_boundary_root() -> None:
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    ) as client:
        model = _native_model(client.release, "OTC-P-0001", "water_level")
        start = float(
            _astro.instant(dt.datetime(2010, 3, 10, 11, 22, 50, tzinfo=dt.timezone.utc))
        )
        stop = float(
            _astro.instant(dt.datetime(2010, 3, 10, 18, 5, 38, tzinfo=dt.timezone.utc))
        )
        expected = _prefilter_native_phase(model.native_sum, start, stop)
        assert any(not start <= math.floor(root[0] + 0.5) < stop for root in expected)
        result = canonical._find_unrounded_tide_events(
            selected_prediction_model=model,
            prediction_window=types._PredictionWindow(start, stop, None, None),
        )
        assert [(r.root_seconds, r.event_type, r.height_m) for r in result] == list(
            expected
        )


def test_m1_B44_actual_current_phase() -> None:
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    ) as client:
        model = _native_model(client.release, "OTC-P-0016", "current")
        start = float(_astro.instant(dt.datetime(2010, 3, 1, tzinfo=dt.timezone.utc)))
        stop = float(_astro.instant(dt.datetime(2010, 3, 3, tzinfo=dt.timezone.utc)))
        # The same native candidate phase now has an exact private entry. Before
        # extraction the RED witness selected that phase through native tracing.
        expected = _engine._unrounded_current_events(
            model.native_context, start, stop, event_source=_prefilter_native_phase
        )
        assert any(not start <= math.floor(root[0] + 0.5) < stop for root in expected)
        at, end = _astro.utc(start), _astro.utc(stop)
        request = types._Arguments18(
            "Release.current_events", "OTC-P-0016", at, end, None, None
        )
        result = canonical._find_unrounded_current_events(
            selected_prediction_model=model,
            prediction_window=types._PredictionWindow(start, stop, None, None),
            current_request=request,
        )
        assert [
            (r.root_seconds, r.event_type, r.velocity_m_s, r.direction_deg)
            for r in result
        ] == expected


@pytest.fixture
def _missing_native_client() -> Iterator[OpenTideConstants]:
    with OpenTideConstants(
        file=ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    ) as client:
        yield client


@pytest.fixture
def _missing_native_pair() -> Iterator[tuple[OpenTideConstants, OpenTideConstants]]:
    fixture = ROOT / "conformance/fixtures/predict/OTC_20991231.7.json"
    with (
        OpenTideConstants(file=fixture) as left,
        OpenTideConstants(file=fixture) as right,
    ):
        yield left, right


@pytest.fixture
def missing_cases(_missing_native_client):
    client = _missing_native_client
    release = client.release
    station = release.require_station("OTC-P-0001")
    constants = station.recommended_set
    assert constants is not None
    at = dt.datetime(2010, 3, 1, tzinfo=dt.timezone.utc)
    no = types._OMITTED
    cases = {
        "station-id": (
            types._Request6("Release.station", None),
            "station",
            lambda: release.station(None),
        ),
        "alias-system": (
            types._Request7("Release.station_by_alias", None, station.station_id),
            "station_by_alias",
            lambda: release.station_by_alias(None, station.station_id),
        ),
        "alias-id": (
            types._Request7("Release.station_by_alias", _enums.AliasSystem.NOAA, None),
            "station_by_alias",
            lambda: release.station_by_alias("noaa", None),
        ),
        "station-type": (
            types._Request12("Release.reference_station", None),
            "reference_station",
            lambda: release.reference_station(None),
        ),
        "attribution-container": (
            types._Request13("Release.attribution", station.station_id),
            "attribution",
            lambda: release.attribution(station.station_id),
        ),
        "attribution-item": (
            types._Request13("Release.attribution", (station, None)),
            "attribution",
            lambda: release.attribution((station, None)),
        ),
        "datums-set": (
            types._Request19("Release.datums", station, True, False),
            "datums",
            lambda: release.datums(station, set_id=True),
        ),
        "datums-all": (
            types._Request19("Release.datums", station, None, 1),
            "datums",
            lambda: release.datums(station, all_sets=1),
        ),
        "ranges-set": (
            types._Request20("Release.ranges", station, True),
            "ranges",
            lambda: release.ranges(station, set_id=True),
        ),
        "astro-id": (
            types._Request21("Release.astro_table", 1),
            "astro_table",
            lambda: release.astro_table(1),
        ),
        "include-no-constants": (
            types._Request22("Station.constant_sets", 1),
            "constant_sets",
            lambda: station.constant_sets(include_no_constants=1),
        ),
        "offset-type": (
            types._Request14("Release.heights", station, at, at, 600, no, no, 1),
            "heights",
            lambda: release.heights(station, start=at, stop=at, offset_id=1),
        ),
        "offset-pair": (
            types._Request14(
                "Release.heights",
                station,
                at,
                at,
                600,
                None,
                constants.set_id,
                constants.set_id,
            ),
            "heights",
            lambda: release.heights(
                station,
                start=at,
                stop=at,
                set_id=constants.set_id,
                offset_id=constants.set_id,
            ),
        ),
    }
    yield cases, release


@pytest.mark.parametrize(
    "case",
    [
        "station-id",
        "alias-system",
        "alias-id",
        "station-type",
        "attribution-container",
        "attribution-item",
        "datums-set",
        "datums-all",
        "ranges-set",
        "astro-id",
        "include-no-constants",
        "offset-type",
        "offset-pair",
    ],
)
def test_missing_native_primitive_guard(missing_cases, case: str) -> None:
    cases, release = missing_cases
    arguments, operation, native = cases[case]
    with pytest.raises(_errors.InvalidArgumentError) as expected:
        native()
    print(f"NATIVE_GUARD {case}: {expected.value.code}: {expected.value}")
    origin_failures = []
    if isinstance(arguments, types._Request13) and isinstance(
        arguments.stations, tuple
    ):
        for station in arguments.stations:
            if isinstance(station, _models.Station):
                try:
                    release.attribution((station,))
                except _errors.InvalidArgumentError as error:
                    origin_failures.append(error)
                else:
                    origin_failures.append(None)
            else:
                origin_failures.append(None)
    contract = types._B01ReleaseContract(
        arguments, release, attribution_origin_failures=tuple(origin_failures)
    )
    with pytest.raises(_errors.InvalidArgumentError) as actual:
        canonical._validate_operation_arguments(
            operation=operation, arguments=arguments, member_contract=contract
        )
    assert str(actual.value) == str(expected.value)


def test_attribution_prior_owner_precedes_later_type(_missing_native_pair) -> None:
    left, right = _missing_native_pair
    foreign = left.release.require_station("OTC-P-0001")
    with pytest.raises(_errors.InvalidArgumentError) as expected:
        right.release.attribution((foreign, None))
    with pytest.raises(_errors.InvalidArgumentError) as prior_owner:
        right.release.attribution((foreign,))
    arguments = types._Request13("Release.attribution", (foreign, None))
    contract = types._B01ReleaseContract(
        arguments, right.release, attribution_origin_failures=(prior_owner.value, None)
    )
    with pytest.raises(_errors.InvalidArgumentError) as actual:
        canonical._validate_operation_arguments(
            operation="attribution", arguments=arguments, member_contract=contract
        )
    assert actual.value is prior_owner.value
    assert str(actual.value) == str(expected.value)


def test_closed_receiver_precedes_bad_primitive(_missing_native_client) -> None:
    client = _missing_native_client
    release = client.release
    client.close()
    with pytest.raises(_errors.FileError) as expected:
        release.station(None)
    arguments = types._Request6("Release.station", None)
    contract = types._B01ReleaseContract(arguments, release)
    with pytest.raises(_errors.FileError) as actual:
        canonical._validate_operation_arguments(
            operation="station", arguments=arguments, member_contract=contract
        )
    assert str(actual.value) == str(expected.value)


def test_station_prerequisite_precedes_bad_datum_option(_missing_native_client) -> None:
    client = _missing_native_client
    release = client.release
    with pytest.raises(_errors.StationNotFoundError) as expected:
        release.datums("missing-station", set_id=True)
    with pytest.raises(_errors.StationNotFoundError) as prerequisite:
        release.require_station("missing-station")
    arguments = types._Request19("Release.datums", "missing-station", True, False)
    contract = types._B01ReleaseContract(
        arguments, release, station_error=prerequisite.value
    )
    with pytest.raises(_errors.StationNotFoundError) as actual:
        canonical._validate_operation_arguments(
            operation="datums", arguments=arguments, member_contract=contract
        )
    assert actual.value is prerequisite.value
    assert str(actual.value) == str(expected.value)


@pytest.mark.parametrize("record_index", [6, 7, 12, 13, 14, 15, 16, 19, 20, 21, 22])
def test_raw_request_adapts_to_narrow_arguments(
    _missing_native_client, record_index: int
) -> None:
    release = _missing_native_client.release
    station = release.require_station("OTC-P-0001")
    assert isinstance(station, _models.Station)
    at = dt.datetime(2010, 3, 1, tzinfo=dt.timezone.utc)
    no = types._OMITTED
    cases: dict[
        int, tuple[types._COperation, types._MemberRequests, types._CValidatedArguments]
    ] = {
        6: (
            "station",
            types._Request6("Release.station", station.station_id),
            types._Arguments6("Release.station", station.station_id),
        ),
        7: (
            "station_by_alias",
            types._Request7(
                "Release.station_by_alias", _enums.AliasSystem.NOAA, station.station_id
            ),
            types._Arguments7(
                "Release.station_by_alias", _enums.AliasSystem.NOAA, station.station_id
            ),
        ),
        12: (
            "reference_station",
            types._Request12("Release.reference_station", station),
            types._Arguments12("Release.reference_station", station),
        ),
        13: (
            "attribution",
            types._Request13("Release.attribution", (station,)),
            types._Arguments13("Release.attribution", (station,)),
        ),
        14: (
            "heights",
            types._Request14("Release.heights", station, at, at, 600, no, no, no),
            types._Arguments14("Release.heights", station, at, at, 600, no, no, no),
        ),
        15: (
            "heights_at",
            types._Request15("Release.heights_at", station, (at,), no, no, no),
            types._Arguments15("Release.heights_at", station, (at,), no, no, no),
        ),
        16: (
            "extremes",
            types._Request16("Release.extremes", station, at, at, no, no, no),
            types._Arguments16("Release.extremes", station, at, at, no, no, no),
        ),
        19: (
            "datums",
            types._Request19("Release.datums", station, no, no),
            types._Arguments19("Release.datums", station, no, no),
        ),
        20: (
            "ranges",
            types._Request20("Release.ranges", station, no),
            types._Arguments20("Release.ranges", station, no),
        ),
        21: (
            "astro_table",
            types._Request21("Release.astro_table", no),
            types._Arguments21("Release.astro_table", no),
        ),
        22: (
            "constant_sets",
            types._Request22("Station.constant_sets", no),
            types._Arguments22("Station.constant_sets", no),
        ),
    }
    operation, request, expected = cases[record_index]
    release.attribution((station,))
    context = types._B01ReleaseContract(
        request,
        release,
        attribution_origin_failures=(None,) if record_index == 13 else (),
    )
    actual = canonical._validate_operation_arguments(
        operation=operation, arguments=request, member_contract=context
    )
    assert type(actual) is type(expected) and actual == expected
    assert release.require_station(station.station_id) is station
