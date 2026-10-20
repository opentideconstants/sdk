"""Private canonical leaves and incomplete orchestration seams."""

from __future__ import annotations
from . import _canonical_types as T
from . import _client, _models, _release, _errors
from ._cache_json import encode_cache_json
from ._predict import _engine, _astro, _harmonic, _results
from dataclasses import dataclass, replace
from collections.abc import Mapping
from typing import TypeVar
from . import _enums

_OptionT = TypeVar("_OptionT")


def _specified(value: _OptionT | T._Omitted, default: _OptionT) -> _OptionT:
    return default if isinstance(value, T._Omitted) else value


def _open_options(
    options: T._Arguments0 | T._EffectiveOptions,
) -> T._ConstructorOptions:
    """Native presence projection into the unchanged constructor parameters."""
    return T._ConstructorOptions(
        release=_specified(options.release, "latest"),
        file=_specified(options.file, None),
        cache_dir=_specified(options.cache_dir, None),
        offline=_specified(options.offline, False),
        mode=_specified(options.mode, _enums.Mode.EAGER),
        base_url=_specified(options.base_url, None),
        timeout=_specified(options.timeout, None),
        proxy=_specified(options.proxy, None),
        ca_file=_specified(options.ca_file, None),
        user_agent=_specified(options.user_agent, None),
        on_network_error=_specified(
            options.on_network_error, _enums.OnNetworkError.USE_CACHE
        ),
        auto_update=_specified(options.auto_update, False),
        update_interval=_specified(options.update_interval, 86400.0),
        logger=_specified(options.logger, None),
        verify_on_open=_specified(options.verify_on_open, False),
        commercial_only=_specified(options.commercial_only, False),
        commercial_basis=_specified(options.commercial_basis, "strict"),
        historical_offsets_policy=_specified(
            options.historical_offsets_policy, "fallback"
        ),
    )


def _mutable_source(
    value: T._JsonValue | T._CCacheDocument | T._CRawFields,
) -> T._JsonValue:
    """Only the original raw/source/cache JSON domain; no contract/type erasure."""
    if isinstance(value, Mapping):
        result: dict[str, T._JsonValue] = {}
        for key, item in value.items():
            if item is None or isinstance(
                item, (str, bool, int, float, tuple, list, Mapping)
            ):
                result[key] = _mutable_source(item)
            else:
                raise TypeError(f"unsupported source JSON value: {type(item).__name__}")
        return result
    if isinstance(value, (tuple, list)):
        return [_mutable_source(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class _BoundModel(T._PredictionModel):
    native_sum: _harmonic.Sum
    native_table: _astro.AstroTable
    native_context: _engine._Context
    native_year: int | None = None


class _AstronomyBoundSum:
    """Native evaluation forwarding; numerical formulas stay in the genuine Sum."""

    def __init__(self, source: _harmonic.Sum, model: T._PredictionModel):
        if not isinstance(model, T._PreparedModel):
            raise NotImplementedError("Native selected model owner incomplete")
        self.source = source
        self.table = source.table
        self.model = _BoundModel(
            station=model.station,
            release_view=model.release_view,
            constant_set=model.constant_set,
            convention=model.convention,
            astro_table=model.astro_table,
            required_constituents=model.required_constituents,
            reference_bin=model.reference_bin,
            mean_term=source.mean,
            datum_source=model.datum_source,
            native_sum=source,
            native_table=model.native_table,
            native_context=model.native_context,
        )

    def value(
        self, seconds: float, year: int | None = None, derivative: bool = False
    ) -> float:
        _evaluate_astronomy(
            selected_prediction_model=replace(self.model, native_year=year),
            utc_instant=seconds,
        )
        return self.source.value(seconds, year, derivative)

    def bound(self, year: int, derivative: bool) -> float:
        return self.source.bound(year, derivative)

    def error(self, year: int, a: float, b: float, derivative: bool) -> float:
        return self.source.error(year, a, b, derivative)


def _validate_operation_arguments(
    *,
    operation: T._COperation,
    arguments: T._CArguments,
    member_contract: T._CMemberContract,
) -> T._CValidatedArguments:
    if isinstance(arguments, (T._Arguments14, T._Arguments15, T._Arguments16,
                              T._Arguments17, T._Arguments18)):
        allowed = ('m/s', 'knots') if isinstance(arguments, (T._Arguments17, T._Arguments18)) else ('meters', 'feet')
        if _specified(arguments.units, allowed[0]) not in allowed:
            raise _errors.InvalidArgumentError("unsupported prediction units")
    if isinstance(arguments, T._MemberRequests):
        return _validate_request_arguments(arguments, member_contract)
    if isinstance(arguments, T._Arguments13):
        return _validate_request_arguments(arguments, member_contract)
    if isinstance(arguments, T._Arguments1):
        if arguments.member_id in (
            "Client.releases",
            "Client.latest",
            "Client.check_for_update",
            "Client.update",
            "Client.verify",
            "Client.cached_releases",
        ):
            if (
                not isinstance(member_contract, T._B01ClientReceiver)
                or member_contract.arguments is not arguments
            ):
                raise NotImplementedError("B01 selected Client receiver incomplete")
            client = member_contract.native_client
            client._check_open()
            if arguments.member_id in ("Client.latest", "Client.check_for_update"):
                _client._validate_offline_pointer(client)
            elif arguments.member_id == "Client.update":
                _client._validate_update_capability(client)
        elif arguments.member_id in (
            "Release.conventions",
            "Release.licences",
            "Release.constituent_names",
            "Release.stats",
            "Release.station_count",
            "Release.tombstone_count",
            "Release.historical_offsets_policy",
        ):
            if (
                not isinstance(member_contract, T._B01ReleaseReceiver)
                or member_contract.arguments is not arguments
            ):
                raise NotImplementedError("B01 selected Release receiver incomplete")
            member_contract.native_release._check_open()
        return arguments
    if isinstance(arguments, T._Arguments0):
        if member_contract.member_id != arguments.member_id:
            raise _errors.InvalidArgumentError(
                "member contract does not match operation"
            )
        options = _open_options(arguments)
        _client._validate_constructor_options(
            release=options.release,
            file=options.file,
            offline=options.offline,
            mode=options.mode,
            on_network_error=options.on_network_error,
            auto_update=options.auto_update,
            verify_on_open=options.verify_on_open,
            commercial_only=options.commercial_only,
            commercial_basis=options.commercial_basis,
            historical_offsets_policy=options.historical_offsets_policy,
            timeout=options.timeout,
            update_interval=options.update_interval,
        )
        if options.base_url is not None:
            _client.check_http_url("base_url", options.base_url)
        _client._check_user_agent(options.user_agent)
        if options.proxy is not None:
            _client.check_http_url("proxy", options.proxy)
        return arguments
    if isinstance(arguments, T._Arguments2):
        _client._validate_download_arguments(
            release=_specified(arguments.release, "latest"),
            formats=_specified(arguments.formats, (_enums.Format.JSONL,)),
            overwrite=_specified(arguments.overwrite, False),
            to=arguments.to,
        )
    elif isinstance(arguments, T._Arguments3):
        _client._validate_prune_arguments(_specified(arguments.keep, 3))
    elif isinstance(
        arguments, (T._Arguments8, T._Arguments9, T._Arguments10, T._Arguments11)
    ):
        if isinstance(arguments, T._Arguments9):
            _release._validate_search_arguments(
                arguments.name,
                _specified(arguments.limit, None),
                _specified(arguments.match, None),
            )
        elif isinstance(arguments, T._Arguments10):
            arguments = replace(
                arguments,
                lat=_release._number("lat", arguments.lat, -90, 90),
                lon=_release._number("lon", arguments.lon, -180, 180),
                radius_km=_release._number("radius_km", arguments.radius_km, 0),
            )
            _release._limit(_specified(arguments.limit, None))
        elif isinstance(arguments, T._Arguments11):
            arguments = replace(
                arguments,
                lat=_release._number("lat", arguments.lat, -90, 90),
                lon=_release._number("lon", arguments.lon, -180, 180),
                max_km=_release._number(
                    "max_km", _specified(arguments.max_km, None), 0, allow_none=True
                ),
            )
        _release._validate_station_filters(
            _specified(arguments.country, None),
            _specified(arguments.type, None),
            _specified(arguments.kind, None),
            _specified(arguments.source, None),
            _specified(arguments.source_type, None),
            _specified(arguments.include_flagged, False),
            _specified(arguments.include_fallback, False),
        )
    elif isinstance(
        arguments, (T._Arguments14, T._Arguments16, T._Arguments17, T._Arguments18)
    ):
        if isinstance(arguments, (T._Arguments14, T._Arguments17)):
            _engine._window(
                arguments.start, arguments.stop, _specified(arguments.step_s, 600)
            )
        else:
            _engine._window(arguments.start, arguments.stop)
        datum = (
            _specified(arguments.datum, None)
            if isinstance(arguments, (T._Arguments14, T._Arguments16))
            else None
        )
        bin_number = (
            _specified(arguments.bin_number, None)
            if isinstance(arguments, (T._Arguments17, T._Arguments18))
            else None
        )
        _engine._options(_specified(arguments.set_id, None), datum, bin_number)
        if isinstance(arguments, (T._Arguments14, T._Arguments16)):
            _engine._validate_offset_arguments(
                _specified(arguments.offset_id, None),
                _specified(arguments.set_id, None),
            )
    elif isinstance(arguments, T._Arguments15):
        for instant in arguments.times:
            _astro.instant(instant)
        _engine._options(
            _specified(arguments.set_id, None), _specified(arguments.datum, None)
        )
        _engine._validate_offset_arguments(
            _specified(arguments.offset_id, None), _specified(arguments.set_id, None)
        )
    elif isinstance(arguments, T._Arguments6):
        _release._check_type(
            "station_id", arguments.station_id, (str,), allow_none=False
        )
    elif isinstance(arguments, T._Arguments7):
        _release._check_type("system", arguments.system, (str,), allow_none=False)
        _release._check_type("alias_id", arguments.alias_id, (str,), allow_none=False)
    elif isinstance(arguments, T._Arguments12):
        _release._validate_station_argument(
            arguments.station, arguments.member_id.split(".")[-1]
        )
    elif isinstance(arguments, (T._Arguments19, T._Arguments20)):
        _engine._options(_specified(arguments.set_id, None))
        if isinstance(arguments, T._Arguments19):
            _engine._validate_all_sets(_specified(arguments.all_sets, False))
    elif isinstance(arguments, T._Arguments21):
        _engine._validate_astro_table_id(_specified(arguments.id, None))
    elif isinstance(arguments, T._Arguments22):
        _models._validate_include_no_constants(
            _specified(arguments.include_no_constants, False)
        )
    elif isinstance(arguments, T._Arguments25):
        _astro.instant(arguments.at)
    elif isinstance(arguments, T._Arguments26):
        if isinstance(member_contract, T._AstroMemberContract):
            if member_contract.arguments is not arguments:
                raise NotImplementedError(
                    "B01 selected AstroTable argument binding incomplete"
                )
            member_contract.native_table._row(arguments.name)
        _astro._validate_year(arguments.year)
    # Remaining closed records have no additional primitive/value checks on their
    # genuine reference routes. Model ownership, domain and localization stay with
    # their separately named operations.
    return arguments


def _validate_request_arguments(
    arguments: T._MemberRequests | T._Arguments13, member_contract: T._CMemberContract
) -> T._CValidatedArguments:
    prepared = (
        member_contract if isinstance(member_contract, T._B01ReleaseContract) else None
    )
    if prepared is not None:
        if prepared.arguments is not arguments:
            raise NotImplementedError("B01 prepared argument identity incomplete")
        prepared.native_release._check_open()
    if isinstance(arguments, T._Request6):
        _release._check_type(
            "station_id", arguments.station_id, (str,), allow_none=False
        )
        assert isinstance(arguments.station_id, str)
        return T._Arguments6(arguments.member_id, arguments.station_id)
    if isinstance(arguments, T._Request7):
        _release._check_type("system", arguments.system, (str,), allow_none=False)
        _release._check_type("alias_id", arguments.alias_id, (str,), allow_none=False)
        assert isinstance(arguments.system, _enums.AliasSystem)
        assert isinstance(arguments.alias_id, str)
        return T._Arguments7(arguments.member_id, arguments.system, arguments.alias_id)
    if isinstance(arguments, T._Request12):
        _release._validate_station_argument(
            arguments.station, arguments.member_id.split(".")[-1]
        )
        assert isinstance(arguments.station, _models.Station)
        return T._Arguments12(arguments.member_id, arguments.station)
    if isinstance(arguments, (T._Request13, T._Arguments13)):
        stations = _specified(arguments.stations, None)
        _release._validate_attribution_container(stations)
        if stations is None:
            original = arguments.stations
            return T._Arguments13(
                arguments.member_id,
                original if isinstance(original, T._Omitted) else None,
            )
        assert isinstance(stations, tuple)
        if prepared is None or len(prepared.attribution_origin_failures) != len(
            stations
        ):
            raise NotImplementedError(
                "B01 attribution ordered origin prerequisites incomplete"
            )
        validated = []
        for index, station in enumerate(stations):
            _release._validate_attribution_item(station)
            failure = prepared.attribution_origin_failures[index]
            if failure is not None:
                raise failure
            assert isinstance(station, _models.Station)
            validated.append(station)
        return T._Arguments13(arguments.member_id, tuple(validated))
    if isinstance(arguments, (T._Request14, T._Request15, T._Request16)):
        if _specified(arguments.units, 'meters') not in ('meters', 'feet'):
            raise _errors.InvalidArgumentError("unsupported prediction units")
        if isinstance(arguments, T._Request15):
            for instant in arguments.times:
                _astro.instant(instant)
        elif isinstance(arguments, T._Request14):
            _engine._window(
                arguments.start, arguments.stop, _specified(arguments.step_s, 600)
            )
        else:
            _engine._window(arguments.start, arguments.stop)
        if prepared is not None and prepared.station_error is not None:
            raise prepared.station_error
        _engine._options(
            _specified(arguments.set_id, None), _specified(arguments.datum, None)
        )
        _engine._validate_offset_arguments(
            _specified(arguments.offset_id, None), _specified(arguments.set_id, None)
        )
        offset = arguments.offset_id
        assert offset is None or isinstance(offset, (str, T._Omitted))
        if isinstance(arguments, T._Request14):
            return T._Arguments14(
                arguments.member_id,
                arguments.station,
                arguments.start,
                arguments.stop,
                arguments.step_s,
                arguments.datum,
                arguments.set_id,
                offset,
                units=arguments.units,
            )
        if isinstance(arguments, T._Request15):
            return T._Arguments15(
                arguments.member_id,
                arguments.station,
                arguments.times,
                arguments.datum,
                arguments.set_id,
                offset,
                units=arguments.units,
            )
        return T._Arguments16(
            arguments.member_id,
            arguments.station,
            arguments.start,
            arguments.stop,
            arguments.datum,
            arguments.set_id,
            offset,
            units=arguments.units,
        )
    if isinstance(arguments, (T._Request19, T._Request20)):
        if prepared is not None and prepared.station_error is not None:
            raise prepared.station_error
        _engine._options(_specified(arguments.set_id, None))
        set_id = arguments.set_id
        assert set_id is None or isinstance(set_id, (str, T._Omitted))
        if isinstance(arguments, T._Request19):
            _engine._validate_all_sets(_specified(arguments.all_sets, False))
            assert isinstance(arguments.all_sets, (bool, T._Omitted))
            return T._Arguments19(
                arguments.member_id, arguments.station, set_id, arguments.all_sets
            )
        return T._Arguments20(arguments.member_id, arguments.station, set_id)
    if isinstance(arguments, T._Request21):
        _engine._validate_astro_table_id(_specified(arguments.id, None))
        assert arguments.id is None or isinstance(arguments.id, (str, T._Omitted))
        return T._Arguments21(arguments.member_id, arguments.id)
    _models._validate_include_no_constants(
        _specified(arguments.include_no_constants, False)
    )
    assert isinstance(arguments.include_no_constants, (bool, T._Omitted))
    return T._Arguments22(arguments.member_id, arguments.include_no_constants)


def _resolve_effective_options(
    *,
    explicit_options: T._CExplicitOptions,
    environment: T._CEnvironment,
    platform_defaults: T._CPlatformDefaults,
) -> T._CEffectiveOptions:
    options = _open_options(explicit_options)
    platform = _open_options(platform_defaults)
    offline, base, cache_dir, interval = _client._resolve_constructor_defaults(
        offline=options.offline,
        base_url=options.base_url,
        cache_dir=options.cache_dir,
        update_interval=options.update_interval,
        environment=environment,
        platform_cache_dir=platform.cache_dir,
    )
    return T._EffectiveOptions(
        release=options.release,
        file=options.file,
        cache_dir=cache_dir,
        offline=offline,
        mode=options.mode,
        base_url=base,
        timeout=options.timeout,
        proxy=options.proxy,
        ca_file=options.ca_file,
        user_agent=options.user_agent,
        on_network_error=options.on_network_error,
        auto_update=options.auto_update,
        update_interval=interval,
        logger=options.logger,
        verify_on_open=options.verify_on_open,
        commercial_only=options.commercial_only,
        commercial_basis=options.commercial_basis,
        historical_offsets_policy=options.historical_offsets_policy,
    )


def _select_canonical_error(
    *, operation: T._COperation, ordered_failures: T._COrderedFailures, cause: T._CCause
) -> T._CCanonicalError:
    if not ordered_failures:
        raise NotImplementedError("B03 has no selected native failure")
    failure = ordered_failures[0]
    return failure if failure.cause is cause else replace(failure, cause=cause)


def _translate_native_binding(
    *,
    canonical_result: T._CCanonicalResult,
    canonical_error: T._CCanonicalError,
    native_profile: T._CNativeProfile,
) -> T._CNativeResult:
    if native_profile != "python":
        raise NotImplementedError("B04 requires the actual Python native binding")
    if not isinstance(canonical_result, T._Absent):
        if (
            isinstance(canonical_error, T._PresentError)
            and canonical_error.member_id != canonical_result.member_id
        ):
            raise _errors.InvalidArgumentError(
                "result and error select different members"
            )
        if isinstance(canonical_result, T._SuccessfulNoValue):
            return None
        return canonical_result.value
    error = (
        canonical_error.error
        if isinstance(canonical_error, T._PresentError)
        else canonical_error
    )
    if isinstance(error, T._NativeFailureOwner):
        raise error.native_error
    raise NotImplementedError("B04 selected native error owner incomplete")


def _decode_release_document(
    *,
    source_bytes: T._CSourceBytes,
    reader_version: T._CReaderVersion,
    document_kind: T._CDocumentKind,
) -> T._CParsedDocument:
    if (reader_version.major, reader_version.minor) != _release.version_key(_release.SUPPORTED_FORMAT_VERSION):
        raise NotImplementedError("B05 native reader version context incomplete")
    what = source_bytes.name if isinstance(source_bytes, T._DocumentSource) else document_kind
    data = source_bytes.data if isinstance(source_bytes, T._DocumentSource) else source_bytes
    document = _release._json(data, what)
    if document_kind == "release":
        _release._check_meta(document, what)
        header = _release._validate_release_header(document)
        _models.parse_time(header.get("created"), "release.created")
    elif document_kind == "station_row":
        if not isinstance(document, dict) or "station_id" not in document:
            raise _errors.InvalidReleaseError(f"{what}: not a station")
        if _release._status(document) == "active":
            _models.check_station_types(document)
    elif document_kind in ("pointer", "catalogue"):
        if not isinstance(source_bytes, T._DocumentSource) or source_bytes.native_client is None:
            raise NotImplementedError("B05 native metadata validation context incomplete")
        if document_kind == "pointer":
            source_bytes.native_client._info(document, source_bytes.name)
        else:
            source_bytes.native_client._index_infos(document, source_bytes.name)
    return document


def _validate_release_links(
    *, parsed_document: T._CParsedDocument, required_links: T._CRequiredLinks
) -> T._CValidatedReleaseGraph:
    document = _mutable_source(parsed_document)
    if not isinstance(document, dict):
        raise NotImplementedError("B06 native station source binding incomplete")
    rows = document.get("stations")
    if not isinstance(rows, list):
        raise NotImplementedError("B06 native station source binding incomplete")
    _release._refs(document, "the release")
    try:
        entries = [_release._entry(row) for row in rows]
    except (KeyError, TypeError, AttributeError) as error:
        raise _errors.InvalidReleaseError(f"bad station or reference data: {error!r}") from error
    _release._resolve_kinds(entries)
    for row in rows:
        _release._validate_refs(row, required_links.conventions, required_links.licences)
    convention_rows, licence_rows = document.get("conventions") or (), document.get("licences") or ()
    assert isinstance(convention_rows, (list, tuple)) and isinstance(licence_rows, (list, tuple))
    _release._check_ids(
        entries,
        [_models.Convention._parse(value) for value in convention_rows],
        [_models.Licence._parse(value) for value in licence_rows],
    )
    return parsed_document


def _materialize_typed_model(
    *,
    raw_fields: T._CRawFields,
    field_contract: T._CFieldContract,
    origin: T._COrigin,
    model_type: T._CModelType,
) -> T._CTypedModel:
    if model_type == "FileInfo" and isinstance(field_contract, T._FileInfoModelFields):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError("B07 prepared FileInfo source binding incomplete")
        return _models.FileInfo(
            name=field_contract.raw_fields["name"],
            url=field_contract.raw_fields["url"],
            size=field_contract.raw_fields["size"],
            sha256=field_contract.raw_fields["sha256"],
        )
    if model_type == "ReleaseInfo" and isinstance(
        field_contract, T._ReleaseInfoModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared ReleaseInfo source binding incomplete"
            )
        return _models.ReleaseInfo(
            datestamp=field_contract.raw_fields["datestamp"],
            format_version=field_contract.raw_fields["format_version"],
            concept_doi=field_contract.raw_fields["concept_doi"],
            zenodo_version_doi=field_contract.raw_fields["zenodo_version_doi"],
            content_sha256=field_contract.raw_fields["content_sha256"],
            files=field_contract.native_files,
            _min_reader_version=field_contract.native_min_reader_version,
        )
    if model_type == "UpdateResult" and isinstance(
        field_contract, T._UpdateResultModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared UpdateResult source binding incomplete"
            )
        return _models.UpdateResult(
            updated=field_contract.raw_fields["updated"],
            from_=field_contract.raw_fields["from_"],
            to=field_contract.raw_fields["to"],
        )
    if model_type == "Nearby" and isinstance(field_contract, T._NearbyModelFields):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError("B07 prepared Nearby source binding incomplete")
        return _models.Nearby(
            station=field_contract.native_station,
            distance_km=field_contract.raw_fields["distance_km"],
        )
    if model_type == "Stats" and isinstance(field_contract, T._StatsModelFields):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError("B07 prepared Stats source binding incomplete")
        return _models.Stats(
            type=field_contract.raw_fields["type"],
            kind=field_contract.raw_fields["kind"],
            country=field_contract.raw_fields["country"],
            source=field_contract.raw_fields["source"],
            qc_status=field_contract.raw_fields["qc_status"],
        )
    if model_type == "HeightPoint" and isinstance(
        field_contract, T._HeightPointModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared HeightPoint source binding incomplete"
            )
        return _results.HeightPoint(
            units=field_contract.raw_fields.get("units", "meters"),
            time=field_contract.native_time,
            height_m=field_contract.raw_fields["height_m"],
            local_time=field_contract.raw_fields["local_time"],
            utc_offset_s=field_contract.raw_fields["utc_offset_s"],
            _local=field_contract.native_local,
        )
    if model_type == "Extreme" and isinstance(field_contract, T._ExtremeModelFields):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError("B07 prepared Extreme source binding incomplete")
        return _results.Extreme(
            units=field_contract.raw_fields.get("units", "meters"),
            time=field_contract.native_time,
            type=field_contract.raw_fields["type"],
            height_m=field_contract.raw_fields["height_m"],
            local_time=field_contract.raw_fields["local_time"],
            utc_offset_s=field_contract.raw_fields["utc_offset_s"],
            _local=field_contract.native_local,
        )
    if model_type == "CurrentPoint" and isinstance(
        field_contract, T._CurrentPointModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared CurrentPoint source binding incomplete"
            )
        return _results.CurrentPoint(
            units=field_contract.raw_fields.get("units", "m/s"),
            time=field_contract.native_time,
            velocity_major_ms=field_contract.raw_fields["velocity_major_ms"],
            velocity_minor_ms=field_contract.raw_fields["velocity_minor_ms"],
            speed_ms=field_contract.raw_fields["speed_ms"],
            direction_deg=field_contract.raw_fields["direction_deg"],
            local_time=field_contract.raw_fields["local_time"],
            utc_offset_s=field_contract.raw_fields["utc_offset_s"],
            _local=field_contract.native_local,
        )
    if model_type == "CurrentEvent" and isinstance(
        field_contract, T._CurrentEventModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared CurrentEvent source binding incomplete"
            )
        return _results.CurrentEvent(
            units=field_contract.raw_fields.get("units", "m/s"),
            time=field_contract.native_time,
            type=field_contract.raw_fields["type"],
            velocity_ms=field_contract.raw_fields["velocity_ms"],
            direction_deg=field_contract.raw_fields["direction_deg"],
            local_time=field_contract.raw_fields["local_time"],
            utc_offset_s=field_contract.raw_fields["utc_offset_s"],
            _local=field_contract.native_local,
        )
    if model_type == "HeightSeries" and isinstance(
        field_contract, T._HeightSeriesModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared HeightSeries source binding incomplete"
            )
        return _results.HeightSeries(
            units=field_contract.raw_fields.get("units", "meters"),
            items=field_contract.native_items,
            station_id=field_contract.raw_fields["station_id"],
            timezone=field_contract.raw_fields["timezone"],
            method=field_contract.raw_fields["method"],
            set_id=field_contract.raw_fields["set_id"],
            convention_id=field_contract.raw_fields["convention_id"],
            astro_table_id=field_contract.raw_fields["astro_table_id"],
            reference_station_id=field_contract.raw_fields["reference_station_id"],
            reference_bin=field_contract.raw_fields["reference_bin"],
            datum=field_contract.raw_fields["datum"],
            datum_name=field_contract.raw_fields["datum_name"],
            datum_kind=field_contract.raw_fields["datum_kind"],
            datum_uncertainty_m=field_contract.raw_fields["datum_uncertainty_m"],
            tz=field_contract.raw_fields["tz"],
            tz_version=field_contract.raw_fields["tz_version"],
            release=field_contract.raw_fields["release"],
            algorithm=field_contract.raw_fields["algorithm"],
            offset_id=field_contract.raw_fields["offset_id"],
            offset_source=field_contract.raw_fields["offset_source"],
            offset_source_version=field_contract.raw_fields["offset_source_version"],
            historical_offsets=field_contract.raw_fields["historical_offsets"],
            current_validity=field_contract.raw_fields["current_validity"],
            current_accuracy=field_contract.raw_fields["current_accuracy"],
            reference_set_id=field_contract.raw_fields["reference_set_id"],
            reference_source_version=field_contract.raw_fields[
                "reference_source_version"
            ],
            reference_2020_equivalence=field_contract.raw_fields[
                "reference_2020_equivalence"
            ],
            source_note=field_contract.raw_fields["source_note"],
        )
    if model_type == "ExtremeList" and isinstance(
        field_contract, T._ExtremeListModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared ExtremeList source binding incomplete"
            )
        return _results.ExtremeList(
            units=field_contract.raw_fields.get("units", "meters"),
            items=field_contract.native_items,
            station_id=field_contract.raw_fields["station_id"],
            timezone=field_contract.raw_fields["timezone"],
            method=field_contract.raw_fields["method"],
            set_id=field_contract.raw_fields["set_id"],
            convention_id=field_contract.raw_fields["convention_id"],
            astro_table_id=field_contract.raw_fields["astro_table_id"],
            reference_station_id=field_contract.raw_fields["reference_station_id"],
            reference_bin=field_contract.raw_fields["reference_bin"],
            datum=field_contract.raw_fields["datum"],
            datum_name=field_contract.raw_fields["datum_name"],
            datum_kind=field_contract.raw_fields["datum_kind"],
            datum_uncertainty_m=field_contract.raw_fields["datum_uncertainty_m"],
            tz=field_contract.raw_fields["tz"],
            tz_version=field_contract.raw_fields["tz_version"],
            release=field_contract.raw_fields["release"],
            algorithm=field_contract.raw_fields["algorithm"],
            offset_id=field_contract.raw_fields["offset_id"],
            offset_source=field_contract.raw_fields["offset_source"],
            offset_source_version=field_contract.raw_fields["offset_source_version"],
            historical_offsets=field_contract.raw_fields["historical_offsets"],
            current_validity=field_contract.raw_fields["current_validity"],
            current_accuracy=field_contract.raw_fields["current_accuracy"],
            reference_set_id=field_contract.raw_fields["reference_set_id"],
            reference_source_version=field_contract.raw_fields[
                "reference_source_version"
            ],
            reference_2020_equivalence=field_contract.raw_fields[
                "reference_2020_equivalence"
            ],
            source_note=field_contract.raw_fields["source_note"],
        )
    if model_type == "CurrentSeries" and isinstance(
        field_contract, T._CurrentSeriesModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared CurrentSeries source binding incomplete"
            )
        return _results.CurrentSeries(
            units=field_contract.raw_fields.get("units", "m/s"),
            items=field_contract.native_items,
            station_id=field_contract.raw_fields["station_id"],
            timezone=field_contract.raw_fields["timezone"],
            method=field_contract.raw_fields["method"],
            set_id=field_contract.raw_fields["set_id"],
            convention_id=field_contract.raw_fields["convention_id"],
            astro_table_id=field_contract.raw_fields["astro_table_id"],
            reference_station_id=field_contract.raw_fields["reference_station_id"],
            reference_bin=field_contract.raw_fields["reference_bin"],
            datum=field_contract.raw_fields["datum"],
            datum_name=field_contract.raw_fields["datum_name"],
            datum_kind=field_contract.raw_fields["datum_kind"],
            datum_uncertainty_m=field_contract.raw_fields["datum_uncertainty_m"],
            bin_number=field_contract.raw_fields["bin_number"],
            tz=field_contract.raw_fields["tz"],
            tz_version=field_contract.raw_fields["tz_version"],
            release=field_contract.raw_fields["release"],
            algorithm=field_contract.raw_fields["algorithm"],
        )
    if model_type == "CurrentEventList" and isinstance(
        field_contract, T._CurrentEventListModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared CurrentEventList source binding incomplete"
            )
        return _results.CurrentEventList(
            units=field_contract.raw_fields.get("units", "m/s"),
            items=field_contract.native_items,
            station_id=field_contract.raw_fields["station_id"],
            timezone=field_contract.raw_fields["timezone"],
            method=field_contract.raw_fields["method"],
            set_id=field_contract.raw_fields["set_id"],
            convention_id=field_contract.raw_fields["convention_id"],
            astro_table_id=field_contract.raw_fields["astro_table_id"],
            reference_station_id=field_contract.raw_fields["reference_station_id"],
            reference_bin=field_contract.raw_fields["reference_bin"],
            datum=field_contract.raw_fields["datum"],
            datum_name=field_contract.raw_fields["datum_name"],
            datum_kind=field_contract.raw_fields["datum_kind"],
            datum_uncertainty_m=field_contract.raw_fields["datum_uncertainty_m"],
            bin_number=field_contract.raw_fields["bin_number"],
            omitted_event_types=field_contract.raw_fields["omitted_event_types"],
            tz=field_contract.raw_fields["tz"],
            tz_version=field_contract.raw_fields["tz_version"],
            release=field_contract.raw_fields["release"],
            algorithm=field_contract.raw_fields["algorithm"],
        )
    if model_type == "DatumInfo" and isinstance(
        field_contract, T._DatumInfoModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared DatumInfo source binding incomplete"
            )
        return _results.DatumInfo(
            set_id=field_contract.raw_fields["set_id"],
            zero=field_contract.raw_fields["zero"],
            zero_name=field_contract.raw_fields["zero_name"],
            chart_datum=field_contract.raw_fields["chart_datum"],
            msl_offset_m=field_contract.raw_fields["msl_offset_m"],
            levels=field_contract.native_levels,
        )
    if model_type == "DatumLevel" and isinstance(
        field_contract, T._DatumLevelModelFields
    ):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError(
                "B07 prepared DatumLevel source binding incomplete"
            )
        return _results.DatumLevel(
            key=field_contract.raw_fields["key"],
            value_m=field_contract.raw_fields["value_m"],
            above_chart_m=field_contract.raw_fields["above_chart_m"],
            kind=field_contract.raw_fields["kind"],
            method=field_contract.raw_fields["method"],
            source_name=field_contract.raw_fields["source_name"],
            epoch=field_contract.raw_fields["epoch"],
            data_span=field_contract.raw_fields["data_span"],
            control_station_id=field_contract.raw_fields["control_station_id"],
            control_set_id=field_contract.raw_fields["control_set_id"],
            control_source_id=field_contract.raw_fields["control_source_id"],
            uncertainty_m=field_contract.raw_fields["uncertainty_m"],
            uncertainty_basis=field_contract.raw_fields["uncertainty_basis"],
            flags=field_contract.raw_fields["flags"],
        )
    if model_type == "Ranges" and isinstance(field_contract, T._RangesModelFields):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError("B07 prepared Ranges source binding incomplete")
        return _results.Ranges(
            mn=field_contract.raw_fields["mn"],
            gt=field_contract.raw_fields["gt"],
            dhq=field_contract.raw_fields["dhq"],
            dlq=field_contract.raw_fields["dlq"],
        )
    if model_type == "Client" and isinstance(field_contract, T._ClientModelFields):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError("B07 prepared Client source binding incomplete")
        receiver = _client.OpenTideConstants.__new__(_client.OpenTideConstants)
        _client._bind_client_fields_1(
            receiver,
            log=field_contract.native_log,
        )
        _client._bind_client_fields_2(
            receiver,
            lock=field_contract.native_lock,
        )
        _client._bind_client_fields_3(
            receiver,
            release=field_contract.native_release,
            loaded_from=field_contract.native_loaded_from,
            last_error=field_contract.native_last_error,
            newer_format_major=field_contract.raw_fields["_newer_format_major"],
            closed=field_contract.raw_fields["_closed"],
        )
        _client._bind_client_fields_4(
            receiver,
            handed_out=field_contract.native_handed_out,
        )
        _client._bind_client_fields_5(
            receiver,
            historical_offsets_policy=field_contract.raw_fields[
                "_historical_offsets_policy"
            ],
        )
        _client._bind_client_fields_6(
            receiver,
            pinned=field_contract.raw_fields["_pinned"],
        )
        _client._bind_client_fields_7(
            receiver,
            file=field_contract.native_file,
        )
        _client._bind_client_fields_8(
            receiver,
            mode=field_contract.raw_fields["_mode"],
        )
        _client._bind_client_fields_9(
            receiver,
            offline=field_contract.raw_fields["_offline"],
        )
        _client._bind_client_fields_10(
            receiver,
            base_url=field_contract.raw_fields["_base_url"],
        )
        _client._bind_client_fields_11(
            receiver,
            cache=field_contract.native_cache,
        )
        _client._bind_client_fields_12(
            receiver,
            on_network_error=field_contract.raw_fields["_on_network_error"],
            auto_update=field_contract.raw_fields["_auto_update"],
        )
        _client._bind_client_fields_13(
            receiver,
            update_interval=field_contract.raw_fields["_update_interval"],
        )
        _client._bind_client_fields_14(
            receiver,
            verify_on_open=field_contract.raw_fields["_verify_on_open"],
        )
        _client._bind_client_fields_15(
            receiver,
            commercial_only=field_contract.raw_fields["_commercial_only"],
            commercial_basis=field_contract.raw_fields["_commercial_basis"],
        )
        _client._bind_client_fields_16(
            receiver,
            http=field_contract.native_http,
        )
        _client._bind_client_fields_17(
            receiver,
            last_check=field_contract.native_last_check,
        )
        return receiver
    if model_type == "Release" and isinstance(field_contract, T._ReleaseModelFields):
        if field_contract.raw_fields is not raw_fields:
            raise NotImplementedError("B07 prepared Release source binding incomplete")
        receiver = _release.Release.__new__(_release.Release)
        _release._bind_release_fields_1(
            receiver,
            historical_offsets_policy=field_contract.raw_fields[
                "_historical_offsets_policy"
            ],
            astro_cache=field_contract.native_astro_cache,
            meta=field_contract.native_meta,
            index_path=field_contract.native_index_path,
        )
        _release._bind_release_fields_2(
            receiver,
            opened=field_contract.native_opened,
        )
        _release._bind_release_fields_3(
            receiver,
            release=field_contract.native_release,
        )
        _release._bind_release_fields_4(
            receiver,
            files=field_contract.native_files,
        )
        _release._bind_release_fields_5(
            receiver,
            conventions=field_contract.native_conventions,
        )
        _release._bind_release_fields_6(
            receiver,
            licences=field_contract.native_licences,
        )
        _release._bind_release_fields_7(
            receiver,
            conv_by_id=field_contract.native_conv_by_id,
        )
        _release._bind_release_fields_8(
            receiver,
            lic_by_id=field_contract.native_lic_by_id,
        )
        _release._bind_release_fields_9(
            receiver,
            commercial_only=field_contract.raw_fields["_commercial_only"],
            commercial_basis=field_contract.raw_fields["_commercial_basis"],
        )
        _release._bind_release_fields_10(
            receiver,
            effective=field_contract.native_effective,
        )
        _release._bind_release_fields_11(
            receiver,
            entries=field_contract.native_entries,
        )
        _release._bind_release_fields_12(
            receiver,
            by_id=field_contract.native_by_id,
        )
        _release._bind_release_fields_13(
            receiver,
            tombs=field_contract.native_tombs,
        )
        _release._bind_release_fields_14(
            receiver,
            alias=field_contract.native_alias,
            subs=field_contract.native_subs,
        )
        _release._bind_release_fields_15(
            receiver,
            mode=field_contract.raw_fields["_mode"],
        )
        _release._bind_release_fields_16(
            receiver,
            station_origin=field_contract.native_station_origin,
        )
        _release._bind_release_fields_17(
            receiver,
            stations=field_contract.native_stations,
        )
        _release._bind_release_fields_18(
            receiver,
            tomb_objs=field_contract.native_tomb_objs,
            fh=field_contract.native_fh,
        )
        _release._bind_release_fields_19(
            receiver,
            lock=field_contract.native_lock,
        )
        _release._bind_release_fields_20(
            receiver,
            lru=field_contract.native_lru,
        )
        _release._bind_release_fields_21(
            receiver,
            jsonl=field_contract.native_jsonl,
            constituent_names=field_contract.native_constituent_names,
            stats=field_contract.native_stats,
            closed=field_contract.raw_fields["_closed"],
            zenodo_version_doi=field_contract.raw_fields["_zenodo_version_doi"],
        )
        return receiver
    source = _mutable_source(raw_fields)
    if model_type == "Constituent":
        return _models.Constituent._parse(source)
    if model_type == "Convention":
        return _models.Convention._parse(source)
    if model_type == "Licence":
        return _models.Licence._parse(source)
    if model_type == "Provenance":
        return _models.Provenance._parse(source)
    if model_type == "ProvenanceBuild":
        model = _models.ProvenanceBuild._parse(source)
        if model is not None:
            return model
    if model_type == "TimeBase":
        model = _models.TimeBase._parse(source)
        if model is not None:
            return model
    if model_type == "QcFlag":
        return _models.QcFlag._parse(source)
    if model_type == "DroppedConstituent":
        return _models.DroppedConstituent._parse(source)
    if model_type == "Validation":
        return _models.Validation._parse(source)
    if model_type == "Tombstone":
        return _models.Tombstone._parse(source)
    if model_type == "SubordinateOffsets":
        return _models.SubordinateOffsets._parse(source)
    if model_type == "AstroTable":
        return _astro.AstroTable(source)
    if model_type == "SourceRecord" and isinstance(
        field_contract, T._SourceFieldsOwner
    ):
        return _models.SourceRecord._parse(source, field_contract.licences)
    if model_type == "Fallback":
        model = _models.Fallback._parse(source)
        if model is not None:
            return model
    if model_type == "HistoricalOffsetVintage":
        return _models.HistoricalOffsetVintage._parse(source)
    if model_type == "HistoricalOffsetProvenance":
        return _models.HistoricalOffsetProvenance._parse(source)
    if model_type == "ConstantSet" and isinstance(
        field_contract, T._ConstantSetFieldsOwner
    ):
        return _models._build_constant_set(
            source,
            field_contract.rows,
            field_contract.recommendation,
            field_contract.convention,
            field_contract.licence,
        )
    if model_type == "RecordSpan":
        model = _models._build_record_span(source)
        if model is not None:
            return model
    if model_type == "Datum":
        model = _models._build_datum(source)
        if model is not None:
            return model
    if model_type != "Station" or not isinstance(field_contract, T._StationFieldsOwner):
        raise NotImplementedError("B07 selected native model context incomplete")
    station = _models.build_station(
        source,
        field_contract.conventions,
        field_contract.licences,
        field_contract.kind,
        field_contract.recommendation,
    )
    object.__setattr__(station, "_origin", origin)
    return station


def _access_raw_record(
    *,
    access_kind: T._CAccessKind,
    source_record: T._CSourceRecord,
    station: T._CStation,
    release_origin: T._CReleaseOrigin,
    native_profile: T._CNativeProfile,
) -> T._CRawRecordOrValidStation:
    if access_kind == "raw_record":
        return _retain_raw_source_record(source_record=source_record, native_profile=native_profile)
    return _check_station_origin(station=station, release_origin=release_origin)


def _open_client_release(
    *,
    arguments: T._CArguments,
    environment: T._CEnvironment,
    platform_defaults: T._CPlatformDefaults,
    cache_state: T._CCacheState,
    clock: T._CClock,
    native_profile: T._CNativeProfile,
    reader_version: T._CReaderVersion,
) -> T._CClientAndRelease:
    raise NotImplementedError("B09 construction-only; body incomplete")


def _resolve_release_request(
    *,
    release_request: T._CReleaseRequest,
    effective_options: T._CEffectiveOptions,
    cache_state: T._CCacheState,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CLoadedRelease:
    raise NotImplementedError("B10 construction-only; body incomplete")


def _exchange_release_metadata(
    *,
    metadata_request: T._CMetadataRequest,
    trusted_cache: T._CTrustedCache,
    transport_options: T._CTransportOptions,
    cache_state: T._CCacheState,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CValidatedMetadata:
    raise NotImplementedError("B11 construction-only; body incomplete")


def _update_client_release(
    *,
    client_state: T._CClientState,
    update_request: T._CUpdateRequest,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CUpdatedClientState:
    raise NotImplementedError("B12 construction-only; body incomplete")


def _refresh_client_if_due(
    *,
    client_state: T._CClientState,
    query_kind: T._CQueryKind,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CQueryClientState:
    raise NotImplementedError("B13 construction-only; body incomplete")


def _forward_held_release(
    *, held_release: T._CHeldRelease, query_arguments: T._CQueryArguments
) -> T._CHeldReleaseResult:
    raise NotImplementedError("B14 construction-only; body incomplete")


def _enforce_resource_lifetime(
    *, resource_state: T._CResourceState, lifetime_action: T._CLifetimeAction
) -> T._CResourceStateOrError:
    owner = resource_state.release_view if isinstance(resource_state, T._StreamReader) else resource_state
    if not isinstance(owner, (_release.Release, _client.OpenTideConstants)):
        raise NotImplementedError("B15 native lifetime owner incomplete")
    if lifetime_action == "close":
        if isinstance(owner, _client.OpenTideConstants):
            owner.close()
        else:
            owner._close()
    elif lifetime_action not in ("retained_metadata", "retained_model"):
        owner._check_open()
    if isinstance(resource_state, T._StreamReader):
        return replace(resource_state, closed=owner._closed)
    return resource_state


def _bind_checksum_manifest(
    *,
    checksum_bytes: T._CChecksumBytes,
    pointer_digests: T._CPointerDigests,
    required_files: T._CRequiredFiles,
) -> T._CBoundChecksums:
    data = checksum_bytes.data if isinstance(checksum_bytes, T._ChecksumSource) else checksum_bytes
    what = checksum_bytes.name if isinstance(checksum_bytes, T._ChecksumSource) else ".sha256"
    rows = _client._parse_sha256(data, what)
    paths = []
    for required in required_files:
        if not isinstance(required, str):
            raise NotImplementedError("B16 native required filename binding incomplete")
        paths.append(_client.Path(required))
    if paths:
        remote_mode = checksum_bytes.load_mode if isinstance(checksum_bytes, T._ChecksumSource) else None
        if remote_mode == "stream" or (remote_mode == "eager" and paths[0].name.endswith(".jsonl")):
            for path in paths:
                _client._require_stream_row(path.name, rows)
        else:
            _client._need_rows(paths[0], paths, rows, what)
    if pointer_digests:
        for name, digest in pointer_digests.items():
            if name.endswith(".sha256"):
                _client._check_cached_manifest_bytes(data, _client.Path(name), (digest,))
        _client._check_pointer_digests(pointer_digests, rows)
    return rows


def _acquire_release_files(
    *,
    acquisition_descriptor: T._CAcquisitionDescriptor,
    effective_options: T._CEffectiveOptions,
    load_mode: T._CLoadMode,
    cache_state: T._CCacheState,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CLoadedRelease:
    raise NotImplementedError("B17 construction-only; body incomplete")


def _merge_cache_receipt(
    *,
    locked_cache_state: T._CLockedCacheState,
    verified_file_rows: T._CVerifiedFileRows,
    release_metadata: T._CReleaseMetadata,
) -> T._CMergedReceipt:
    raise NotImplementedError("B18 construction-only; body incomplete")


def _select_cached_release(
    *,
    release_candidates: T._CReleaseCandidates,
    effective_options: T._CEffectiveOptions,
    cache_state: T._CCacheState,
    clock: T._CClock,
) -> T._CUsableCachedReleaseOrError:
    raise NotImplementedError("B19 construction-only; body incomplete")


def _verify_release_files(
    *, release_files: T._CReleaseFiles, trusted_cached_pointer: T._CTrustedCachedPointer
) -> T._CVerificationResult:
    if not isinstance(release_files, _client.OpenTideConstants):
        raise NotImplementedError("B20 native verified file owner incomplete")
    release_files._check_open()
    def bind_manifest(data: bytes, path: _client.Path, digests: T._CPointerDigests):
        return _bind_checksum_manifest(
            checksum_bytes=T._ChecksumSource(data, path.name), pointer_digests=digests, required_files=(),
        )
    return release_files._verify_release_files(
        bind_manifest,
        None if trusted_cached_pointer is None else trusted_cached_pointer.digests,
    )


def _publish_download(
    *,
    destination: T._CDestination,
    format_selection: T._CFormatSelection,
    overwrite_policy: T._COverwritePolicy,
    release_files: T._CReleaseFiles,
    checksum_bytes: T._CChecksumBytes,
    pointer_digests: T._CPointerDigests,
) -> T._CDownloadResult:
    raise NotImplementedError("B21 construction-only; body incomplete")


def _manage_cache_inventory(
    *,
    inventory_action: T._CInventoryAction,
    cache_state: T._CCacheState,
    keep: T._CKeep,
    current_cache_directory: T._CCurrentCacheDirectory,
    clock: T._CClock,
) -> T._CCacheInventoryResult:
    raise NotImplementedError("B22 construction-only; body incomplete")


def _perform_guarded_io(
    *,
    io_kind: T._CIoKind,
    io_request: T._CIoRequest,
    io_options: T._CIoOptions,
    clock: T._CClock,
) -> T._CIoResult:
    raise NotImplementedError("B23 construction-only; body incomplete")


def _project_station_index(
    *,
    station_source_row: T._CStationSourceRow,
    source_byte_span: T._CSourceByteSpan,
    projection_contract: T._CProjectionContract,
) -> T._CStationIndexEntry:
    entry = _release._entry(
        _mutable_source(station_source_row),
        source_byte_span.offset_bytes,
        source_byte_span.length_bytes,
    )
    return T._StationIndexEntry(**entry)


def _authenticate_station_index(
    *,
    source_files: T._CSourceFiles,
    supplied_index: T._CSuppliedIndex,
    index_presence: T._CIndexPresence,
    reader_version: T._CReaderVersion,
) -> T._CAuthenticatedIndex:
    paths = (source_files.jsonl, source_files.meta)
    records = {
        source_files.jsonl.name: {"size": source_files.jsonl_size, "sha256": source_files.jsonl_sha256},
        source_files.meta.name: {"size": source_files.meta_size, "sha256": source_files.meta_sha256},
    }
    _client._authenticate_cached_files(paths, records, True)
    meta = _decode_release_document(
        source_bytes=T._DocumentSource(_release._read_bytes(source_files.meta), str(source_files.meta)),
        reader_version=reader_version, document_kind="release",
    )
    conventions, licences = _release._refs(meta, str(source_files.meta))
    metadata = _mutable_source(meta)
    assert isinstance(metadata, dict)
    convention_rows, licence_rows = metadata.get("conventions") or (), metadata.get("licences") or ()
    assert isinstance(convention_rows, (list, tuple)) and isinstance(licence_rows, (list, tuple))
    native_conventions = [_models.Convention._parse(row) for row in convention_rows]
    native_licences = [_models.Licence._parse(row) for row in licence_rows]
    documents = []
    def project(row, offset: int, length: int):
        return _project_station_index(
            station_source_row=row, source_byte_span=T._SourceByteSpan(offset, length),
            projection_contract=T._ProjectionContract(
                "Exact original canonical field table attached per member; known wrong type is invalid_release, absent nullable is null, missing arrays use each attached contract default. Raw fields preserve source JSON without computed fields.",
                "Model IDs refer to B07, source/ownership objects also B08, historical fields B36, prediction/local/datum results B48. These are value projection behaviors, not an assertion that every getter has an independent algorithm.",
                "Complete source object, including all unknown nested fields, represented by tolerant cache-specific definitions derived from accepted schema33a760ad. Known primitive types, required historical fields, source binding conditions and raw values remain unchanged.",
                "25 scenario families enumerate required shared branches. They are not 25 executed passes or exhaustive binary-branch verification. Each family expands to its incorporated original case table and required additional guard-reaching witnesses.",
                "Complete actual fallback object, including unknown nested fields. String reasons remain source strings in cache/raw and become typed other when unknown. Cache-source comparison includes every preserved field, not only current known keys.",
            ),
        )
    def encode(document):
        return _encode_cache_json(cache_document=document)
    def validate(entries):
        _release._check_ids(entries, native_conventions, native_licences)
        return documents[-1]
    authenticated = _release._stream_index_with_retry(
        source_files.jsonl, conventions, licences, source_files.index_path, source_files.jsonl_sha256,
        validate, project=project, encode=encode,
        supplied=None if supplied_index is None else _mutable_source(supplied_index),
        index_document=documents.append,
    )
    assert authenticated is not None
    return authenticated


def _compare_station_source(
    *,
    index_entry: T._CIndexEntry,
    station_source_row: T._CStationSourceRow,
    index_presence: T._CIndexPresence,
) -> T._CComparedStationRow:
    if not isinstance(index_presence, _release.Release):
        raise NotImplementedError("B26 native index owner incomplete")
    try:
        index_presence._check_line(_mutable_source(station_source_row), index_entry)
    except _errors.InvalidReleaseError as error:
        index_presence._reject_index_mismatch(error)
    return station_source_row


def _read_station_lazily(
    *,
    stream_reader: T._CStreamReader,
    station_id: T._CStationId,
    release_origin: T._CReleaseOrigin,
    reader_version: T._CReaderVersion,
) -> T._CStationSourceRow:
    _enforce_resource_lifetime(resource_state=stream_reader, lifetime_action="station_read")
    owner = stream_reader.release_view if isinstance(stream_reader, T._StreamReader) else stream_reader
    if release_origin is not owner:
        raise NotImplementedError("B27 native producing Release context incomplete")
    entry = owner._by_id.get(station_id)
    if entry is None:
        raise NotImplementedError("B27 native admitted station entry incomplete")
    if isinstance(stream_reader, T._StreamReader):
        if stream_reader.index is not owner._by_id or stream_reader.station_lru is not owner._lru:
            raise NotImplementedError("B27 borrowed native index/cache owner incomplete")
        if stream_reader.index_presence.get(station_id) != entry.get("_index_presence"):
            raise NotImplementedError("B27 borrowed native source presence incomplete")
        if owner._fh is not None and not owner._fh.closed and stream_reader.file_descriptor != owner._fh.fileno():
            raise NotImplementedError("B27 borrowed native descriptor incomplete")
    def decode(data: bytes, what: str):
        return _decode_release_document(
            source_bytes=T._DocumentSource(data, what), reader_version=reader_version, document_kind="station_row",
        )
    def compare(row, native_entry):
        return _compare_station_source(index_entry=native_entry, station_source_row=row, index_presence=owner)
    def read_line(native_entry):
        return owner._read_line(native_entry, decode=decode, compare=compare)
    station = owner._station_from_entry(entry, read_line=read_line)
    return station.raw


def _encode_cache_json(*, cache_document: T._CCacheDocument) -> T._CCacheBytes:
    return encode_cache_json(_mutable_source(cache_document))


def _lookup_station_identity(
    *,
    release_view: T._CReleaseView,
    identity_query: T._CIdentityQuery,
    reader_version: T._CReaderVersion,
) -> T._CStationOrTombstoneOrNull:
    raise NotImplementedError("B29 construction-only; body incomplete")


def _select_effective_recommendation(
    *,
    station_sets: T._CStationSets,
    original_recommendation: T._COriginalRecommendation,
    commercial_only: T._CCommercialOnly,
) -> T._CEffectiveRecommendation:
    raise NotImplementedError("B30 construction-only; body incomplete")


def _admit_quality_path(
    *,
    candidate_path: T._CCandidatePath,
    include_flagged: T._CIncludeFlagged,
    include_fallback: T._CIncludeFallback,
) -> T._CQualityAdmission:
    raise NotImplementedError("B31 construction-only; body incomplete")


def _admit_commercial_path(
    *,
    candidate_path: T._CCandidatePath,
    commercial_only: T._CCommercialOnly,
    commercial_basis: T._CCommercialBasis,
) -> T._CCommercialAdmission:
    raise NotImplementedError("B32 construction-only; body incomplete")


def _resolve_reference_path(
    *,
    station_source_row: T._CStationSourceRow,
    path_request: T._CPathRequest,
    release_view: T._CReleaseView,
) -> T._CSelectedReferencePath:
    raise NotImplementedError("B33 construction-only; body incomplete")


def _execute_discovery_query(
    *,
    release_view: T._CReleaseView,
    query_kind: T._CQueryKind,
    query_options: T._CQueryOptions,
    reader_version: T._CReaderVersion,
) -> T._COrderedStationResults:
    raise NotImplementedError("B34 construction-only; body incomplete")


def _summarize_station_sets(
    *,
    summary_kind: T._CSummaryKind,
    release_view: T._CReleaseView,
    station_sets: T._CStationSets,
    summary_options: T._CSummaryOptions,
) -> T._CStationSummary:
    raise NotImplementedError("B35 construction-only; body incomplete")


def _admit_historical_offset(
    *,
    own_offset: T._COwnOffset,
    reference_path: T._CReferencePath,
    historical_policy: T._CHistoricalPolicy,
    selection_kind: T._CSelectionKind,
    reader_version: T._CReaderVersion,
) -> T._CHistoricalAdmission:
    raise NotImplementedError("B36 construction-only; body incomplete")


def _format_attribution(
    *,
    station: T._CStation,
    release_view: T._CReleaseView,
    commercial_only: T._CCommercialOnly,
) -> T._CAttributionText:
    raise NotImplementedError("B37 construction-only; body incomplete")


def _format_citation(
    *, published_metadata: T._CPublishedMetadata, citation_style: T._CCitationStyle
) -> T._CCitationText:
    raise NotImplementedError("B38 construction-only; body incomplete")


def _parse_prediction_window(
    *,
    time_inputs: T._CTimeInputs,
    window_inputs: T._CWindowInputs,
    step: T._CStep,
    local_time_profile: T._CLocalTimeProfile,
) -> T._CPredictionWindow:
    if isinstance(time_inputs, T._Arguments15):
        instants = tuple(float(_astro.instant(t)) for t in time_inputs.times)
        return T._InstantPredictionWindow(instants)
    if isinstance(
        window_inputs, (T._Arguments14, T._Arguments16, T._Arguments17, T._Arguments18)
    ):
        if isinstance(step, T._Omitted):
            start, stop = _engine._window(window_inputs.start, window_inputs.stop)
            native_step = None
        else:
            start, stop = _engine._window(window_inputs.start, window_inputs.stop, step)
            native_step = step
        return T._PredictionWindow(float(start), float(stop), native_step, None)
    raise NotImplementedError("B39 selected native prediction arguments incomplete")


def _select_prediction_model(
    *,
    station_request: T._CStationRequest,
    release_view: T._CReleaseView,
    selection_options: T._CSelectionOptions,
    reader_version: T._CReaderVersion,
) -> T._CSelectedPredictionModel:
    raise NotImplementedError("B40 construction-only; body incomplete")


def _evaluate_astronomy(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    utc_instant: T._CUtcInstant,
) -> T._CAstronomicalTerms:
    if not isinstance(selected_prediction_model, T._PreparedModel):
        raise NotImplementedError("B41 requires the genuine prepared native receiver")
    year = (
        _astro.utc(utc_instant).year
        if not isinstance(selected_prediction_model, _BoundModel)
        or selected_prediction_model.native_year is None
        else selected_prediction_model.native_year
    )
    origin, terms = selected_prediction_model.native_sum._year(year)
    return T._AstronomicalTerms(year, tuple(terms), (utc_instant - origin) / 3600.0)


def _evaluate_harmonic_height(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_instants: T._CPredictionInstants,
    requested_datum: T._CRequestedDatum,
) -> T._CHeightValues:
    if not isinstance(selected_prediction_model, T._PreparedModel):
        raise NotImplementedError("B42 requires the genuine prepared native receiver")
    context = selected_prediction_model.native_context
    selected_prediction_model.native_sum.mean = _engine._datum(
        selected_prediction_model.constant_set.raw.get("datum"),
        requested_datum,
        context,
    )
    values = []
    for instant in prediction_instants:
        _evaluate_astronomy(
            selected_prediction_model=selected_prediction_model, utc_instant=instant
        )
        values.append(selected_prediction_model.native_sum.value(instant))
    return tuple(values)


def _find_tide_events(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
) -> T._CTideEvents:
    raise NotImplementedError("B43 construction-only; body incomplete")


def _evaluate_direct_current(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
    current_request: T._CCurrentRequest,
    current_operation: T._CCurrentOperation,
) -> T._CDirectCurrentResult:
    raise NotImplementedError("B44 construction-only; body incomplete")


def _evaluate_tide_offset(
    *,
    own_offset: T._COwnOffset,
    reference_path: T._CReferencePath,
    prediction_window: T._CPredictionWindow,
    tide_request: T._CTideRequest,
    reader_version: T._CReaderVersion,
) -> T._COffsetTideResult:
    raise NotImplementedError("B45 construction-only; body incomplete")


def _fold_equal_tide_offset(
    *,
    own_offset: T._COwnOffset,
    reference_model: T._CReferenceModel,
    prediction_instants: T._CPredictionInstants,
    requested_datum: T._CRequestedDatum,
) -> T._CFoldedHeightValues:
    raise NotImplementedError("B46 construction-only; body incomplete")


def _evaluate_current_offset(
    *,
    own_current_offsets: T._COwnCurrentOffsets,
    reference_path: T._CReferencePath,
    prediction_window: T._CPredictionWindow,
    current_request: T._CCurrentRequest,
    reader_version: T._CReaderVersion,
) -> T._COffsetCurrentResult:
    raise NotImplementedError("B47 construction-only; body incomplete")


def _dispatch_auxiliary_result(
    *,
    auxiliary_kind: T._CAuxiliaryKind,
    auxiliary_operation: T._CAuxiliaryOperation,
    source_values: T._CSourceValues,
    result_context: T._CResultContext,
    local_time_profile: T._CLocalTimeProfile,
    result_values: T._CResultValues,
    utc_result: T._CUtcResult,
    selection_options: T._CSelectionOptions,
    reader_version: T._CReaderVersion,
    auxiliary_member_id: T._CAuxiliaryMemberId,
) -> T._CAuxiliaryResult:
    raise NotImplementedError("B48 construction-only; body incomplete")


def _retain_raw_source_record(
    *, source_record: T._CSourceRecord, native_profile: T._CNativeProfile
) -> T._CRawRecord:
    result = _models.freeze(_mutable_source(source_record))
    assert isinstance(result, Mapping)
    return result


def _check_station_origin(
    *, station: T._CStation, release_origin: T._CReleaseOrigin
) -> T._CValidStation:
    if not isinstance(release_origin, _release.Release):
        raise NotImplementedError("B08.origin native producing Release incomplete")
    release_origin._own_station(station, "station")
    return station


def _manage_cache_lock(
    *, lock_request: T._CLockRequest, lock_state: T._CLockState, clock: T._CClock
) -> T._CLockOutcome:
    raise NotImplementedError("B23.lock construction-only; body incomplete")


def _request_http_resource(
    *, http_request: T._CHttpRequest, transport_options: T._CTransportOptions
) -> T._CHttpResponse:
    raise NotImplementedError("B23.http construction-only; body incomplete")


def _count_release_statistics(
    *, release_view: T._CReleaseView
) -> T._CReleaseStatistics:
    raise NotImplementedError("B35.stats construction-only; body incomplete")


def _order_constant_sets(
    *,
    station_sets: T._CStationSets,
    original_recommendation: T._COriginalRecommendation,
    commercial_only: T._CCommercialOnly,
    include_no_constants: T._CIncludeNoConstants,
) -> T._COrderedConstantSets:
    raise NotImplementedError("B35.sets construction-only; body incomplete")


def _read_auxiliary_model_value(
    *,
    auxiliary_operation: T._CAuxiliaryOperation,
    source_values: T._CSourceValues,
    selection_options: T._CSelectionOptions,
    reader_version: T._CReaderVersion,
    auxiliary_member_id: T._CAuxiliaryMemberId,
) -> T._CAuxiliaryModelValue:
    raise NotImplementedError("B48.aux construction-only; body incomplete")


def _construct_prediction_result(
    *, result_values: T._CResultValues, result_context: T._CResultContext
) -> T._CPredictionResult:
    raise NotImplementedError("B48.context construction-only; body incomplete")


def _convert_result_to_local_time(
    *, utc_result: T._CUtcResult, local_time_profile: T._CLocalTimeProfile
) -> T._CLocalTimeResult:
    raise NotImplementedError("B48.local construction-only; body incomplete")


def _find_unrounded_tide_events(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
) -> T._CUnroundedTideEvents:
    if not isinstance(selected_prediction_model, T._PreparedModel):
        raise NotImplementedError(
            "B43.roots requires the genuine prepared native receiver"
        )
    if not isinstance(prediction_window, T._PredictionWindow):
        raise _errors.InvalidArgumentError(
            "event search requires a start and stop window"
        )
    total = _AstronomyBoundSum(
        selected_prediction_model.native_sum, selected_prediction_model
    )
    roots = _harmonic._unrounded_events(
        total, prediction_window.start, prediction_window.stop
    )
    return tuple(
        T._UnroundedTideEvent(t, kind, value, order)
        for order, (t, kind, value) in enumerate(roots)
    )


def _find_unrounded_current_events(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
    current_request: T._CCurrentRequest,
) -> T._CUnroundedCurrentEvents:
    if not isinstance(selected_prediction_model, T._PreparedModel):
        raise NotImplementedError(
            "B44.roots requires the genuine prepared native receiver"
        )
    if not isinstance(prediction_window, T._PredictionWindow):
        raise _errors.InvalidArgumentError(
            "event search requires a start and stop window"
        )

    def source(total: _harmonic.Sum, start: float, stop: float, *, slack: bool = False):
        receiver = _AstronomyBoundSum(total, selected_prediction_model)
        return _harmonic._unrounded_events(receiver, start, stop, slack=slack)

    roots = _engine._unrounded_current_events(
        selected_prediction_model.native_context,
        prediction_window.start,
        prediction_window.stop,
        event_source=source,
    )
    return tuple(
        T._UnroundedCurrentEvent(t, kind, velocity, direction, order)
        for order, (t, kind, velocity, direction) in enumerate(roots)
    )


def _acquire_checksum_sidecar(
    *,
    acquisition_descriptor: T._CAcquisitionDescriptor,
    effective_options: T._CEffectiveOptions,
) -> T._CChecksumBytes:
    raise NotImplementedError("B17.sidecar construction-only; body incomplete")
