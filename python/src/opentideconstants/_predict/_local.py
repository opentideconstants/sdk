"""Lazy IANA zone conversion with the shared zone-name and ISO formatting rules."""
from dataclasses import replace
from pathlib import Path
from importlib import import_module
import re
from .._errors import UnknownTimeZoneError, LocalTimeUnavailableError

_NAME = re.compile(r'\A[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*\Z')


def localize(result, tz):
    import zoneinfo
    zone = result.timezone if tz == 'station' else tz
    if not isinstance(zone, str) or len(zone) > 255 or not _NAME.fullmatch(zone) or zone.startswith(('posix/', 'right/')) or zone in ('posixrules', 'localtime', 'Factory'):
        raise UnknownTimeZoneError(f'unknown time zone {zone!r}', zone=zone)
    system_path = next((Path(p) / zone for p in zoneinfo.TZPATH if (Path(p) / zone).is_file()), None)
    version = None
    has_system = any(Path(p).is_dir() for p in zoneinfo.TZPATH)
    package = None
    try:
        package = import_module('tzdata')
    except ImportError:
        pass
    if not has_system and package is None:
        raise LocalTimeUnavailableError('install opentideconstants[tz] for local time')
    try:
        rules = zoneinfo.ZoneInfo(zone)
    except zoneinfo.ZoneInfoNotFoundError as error:
        raise UnknownTimeZoneError(f'unknown time zone {zone}', zone=zone) from error
    if system_path is not None:
        for root in zoneinfo.TZPATH:
            for name in ('tzdata.zi', '+VERSION'):
                try:
                    first = (Path(root) / name).read_text().splitlines()[0]
                except (OSError, IndexError, UnicodeError):
                    continue
                version = first.removeprefix('# version ').strip() if name == 'tzdata.zi' else first.strip()
                break
            if version is not None:
                break
    elif package is not None:
        version = package.IANA_VERSION
    items = []
    for item in result.items:
        wall = item.time.astimezone(rules)
        offset = int(wall.utcoffset().total_seconds())
        magnitude = abs(offset)
        suffix = f'{"+" if offset >= 0 else "-"}{magnitude // 3600:02d}:{magnitude % 3600 // 60:02d}'
        if magnitude % 60:
            suffix += f':{magnitude % 60:02d}'
        stamp = f'{wall.year:04d}-{wall.month:02d}-{wall.day:02d}T{wall.hour:02d}:{wall.minute:02d}:{wall.second:02d}{suffix}'
        items.append(replace(item, local_time=stamp, utc_offset_s=offset, _local=wall))
    return replace(result, items=tuple(items), tz=zone, tz_version=version)
