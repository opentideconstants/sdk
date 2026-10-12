"""Own-policy admission for the two source-bound NOAA2020 historical profiles."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ._errors import InvalidArgumentError, InvalidReleaseError, NoConstantsError
from ._models import ConstantSet, Licence, _check_historical_offsets


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _immutable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _immutable(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_immutable(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class HistoricalOffsetSelection:
    """Validated own profile and the already-selected, eligible reference."""
    offset_id: str
    offsets: Mapping[str, Any]
    reference: ConstantSet


def historical_offset_eligibility(offsets: Mapping[str, Any], *, policy: str,
                                  licences: Mapping[str, Licence], selected_reference: ConstantSet | None,
                                  better_path: bool, selection: str = "auto",
                                  commercial_only: bool = False) -> bool:
    """Admission independent of query flags; callers decide ordinary-path precedence first.

    The reference is the accepted machinery's selected set, not a list to search for a
    replacement. Existing engine astronomical/window checks still apply to prediction.
    """
    if policy not in ("fallback", "exclude") or selection not in ("auto", "explicit"):
        raise InvalidArgumentError("invalid historical offset policy or selection")
    if not isinstance(better_path, bool) or not isinstance(commercial_only, bool):
        raise InvalidArgumentError("better_path and commercial_only must be booleans")
    if not isinstance(offsets, Mapping) or not isinstance(licences, Mapping):
        raise InvalidArgumentError("offsets and licences must be mappings")
    raw = _plain(offsets)
    _check_historical_offsets(raw)
    if raw.get("offset_id") is None:
        return False
    own_licence = licences.get(raw["licence_id"])
    if not isinstance(own_licence, Licence) or own_licence.licence_id != raw["licence_id"]:
        raise InvalidReleaseError("historical own licence does not resolve")
    if policy == "exclude" or selection == "auto" and better_path:
        return False
    if selected_reference is None:
        return False
    if not isinstance(selected_reference, ConstantSet):
        raise InvalidArgumentError("selected_reference must be a ConstantSet or None")
    reference = selected_reference
    binding = raw["provenance"]["reference_binding"]
    if (not reference.set_id.startswith(raw["reference_station_id"] + "/")
            or reference.source != "noaa" or reference.source_record_id != binding["noaa_id"]
            or reference.quantity != "water_level" or reference.qc_status != "ok" or reference.fallback is not None):
        return False
    reference_licence = licences.get(reference.licence.licence_id)
    if not isinstance(reference_licence, Licence) or reference_licence != reference.licence:
        raise InvalidReleaseError("historical reference licence does not resolve")
    if commercial_only and (own_licence.commercial_use is not True or reference_licence.commercial_use is not True):
        return False
    convention = reference.convention
    if convention.v0_model != "schureman_tcd" or convention.nodal_handling != "f_u_at_prediction":
        return False
    datum = reference.raw.get("datum") or {}
    if (datum.get("chart_datum") != "mllw" or datum.get("msl_offset_m") is None
            or datum.get("named", {}).get("mllw") != 0.0
            or datum.get("basis", {}).get("mllw", {}).get("kind") != "published"):
        return False
    return True


def require_historical_offset(offsets: Mapping[str, Any], *, policy: str,
                              licences: Mapping[str, Licence], selected_reference: ConstantSet | None,
                              better_path: bool, selection: str = "auto",
                              commercial_only: bool = False) -> HistoricalOffsetSelection:
    """The same admission predicate, with an immutable selection or a refusal."""
    eligible = historical_offset_eligibility(offsets, policy=policy, licences=licences,
                                             selected_reference=selected_reference, better_path=better_path,
                                             selection=selection, commercial_only=commercial_only)
    if not eligible:
        raise NoConstantsError("historical offsets are ineligible", policy=policy, selection=selection)
    assert selected_reference is not None
    return HistoricalOffsetSelection(offsets["offset_id"], _immutable(offsets), selected_reference)
