__all__ = [
    "TIMEZONE_ALIASES",
    "all_timezones",
    "country_timezones",
    "localize_standard",
    "timezone",
    "utc",
    "wall_range_to_utc",
    "wall_to_utc",
]

import functools
import itertools
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, tzinfo
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError, available_timezones

utc = UTC

TIMEZONE_ALIASES: dict[str, str] = {
    "Africa/Asmera": "Africa/Nairobi",
    "America/Argentina/ComodRivadavia": "America/Argentina/Catamarca",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Cordoba": "America/Argentina/Cordoba",
    "America/Fort_Wayne": "America/Indiana/Indianapolis",
    "America/Indianapolis": "America/Indiana/Indianapolis",
    "America/Jujuy": "America/Argentina/Jujuy",
    "America/Knox_IN": "America/Indiana/Knox",
    "America/Louisville": "America/Kentucky/Louisville",
    "America/Mendoza": "America/Argentina/Mendoza",
    "America/Rosario": "America/Argentina/Cordoba",
    "Antarctica/South_Pole": "Pacific/Auckland",
    "Asia/Ashkhabad": "Asia/Ashgabat",
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Choibalsan": "Asia/Ulaanbaatar",
    "Asia/Chungking": "Asia/Shanghai",
    "Asia/Dacca": "Asia/Dhaka",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Macao": "Asia/Macau",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Thimbu": "Asia/Thimphu",
    "Asia/Ujung_Pandang": "Asia/Makassar",
    "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    "Australia/ACT": "Australia/Sydney",
    "Australia/LHI": "Australia/Lord_Howe",
    "Australia/North": "Australia/Darwin",
    "Australia/NSW": "Australia/Sydney",
    "Australia/Queensland": "Australia/Brisbane",
    "Australia/South": "Australia/Adelaide",
    "Australia/Tasmania": "Australia/Hobart",
    "Australia/Victoria": "Australia/Melbourne",
    "Australia/West": "Australia/Perth",
    "Brazil/Acre": "America/Rio_Branco",
    "Brazil/DeNoronha": "America/Noronha",
    "Brazil/East": "America/Sao_Paulo",
    "Brazil/West": "America/Manaus",
    "CET": "Europe/Brussels",
    "CST6CDT": "America/Chicago",
    "Canada/Atlantic": "America/Halifax",
    "Canada/Central": "America/Winnipeg",
    "Canada/Eastern": "America/Toronto",
    "Canada/Mountain": "America/Edmonton",
    "Canada/Newfoundland": "America/St_Johns",
    "Canada/Pacific": "America/Vancouver",
    "Canada/Saskatchewan": "America/Regina",
    "Canada/Yukon": "America/Whitehorse",
    "Chile/Continental": "America/Santiago",
    "Chile/EasterIsland": "Pacific/Easter",
    "Cuba": "America/Havana",
    "EET": "Europe/Athens",
    "EST": "America/Panama",
    "EST5EDT": "America/New_York",
    "Egypt": "Africa/Cairo",
    "Eire": "Europe/Dublin",
    "Europe/Kiev": "Europe/Kyiv",
    "Europe/Uzhgorod": "Europe/Kyiv",
    "Europe/Zaporozhye": "Europe/Kyiv",
    "GB": "Europe/London",
    "GB-Eire": "Europe/London",
    "GMT+0": "Etc/GMT",
    "GMT-0": "Etc/GMT",
    "GMT0": "Etc/GMT",
    "Greenwich": "Etc/GMT",
    "HST": "Pacific/Honolulu",
    "Hongkong": "Asia/Hong_Kong",
    "Iceland": "Africa/Abidjan",
    "Iran": "Asia/Tehran",
    "Israel": "Asia/Jerusalem",
    "Jamaica": "America/Jamaica",
    "Japan": "Asia/Tokyo",
    "Kwajalein": "Pacific/Kwajalein",
    "Libya": "Africa/Tripoli",
    "MET": "Europe/Brussels",
    "MST": "America/Phoenix",
    "MST7MDT": "America/Denver",
    "Mexico/BajaNorte": "America/Tijuana",
    "Mexico/BajaSur": "America/Mazatlan",
    "Mexico/General": "America/Mexico_City",
    "Navajo": "America/Denver",
    "NZ": "Pacific/Auckland",
    "NZ-CHAT": "Pacific/Chatham",
    "PST8PDT": "America/Los_Angeles",
    "Pacific/Enderbury": "Pacific/Kanton",
    "Pacific/Ponape": "Pacific/Guadalcanal",
    "Pacific/Truk": "Pacific/Port_Moresby",
    "Poland": "Europe/Warsaw",
    "Portugal": "Europe/Lisbon",
    "PRC": "Asia/Shanghai",
    "ROC": "Asia/Taipei",
    "ROK": "Asia/Seoul",
    "Singapore": "Asia/Singapore",
    "Turkey": "Europe/Istanbul",
    "UCT": "Etc/UTC",
    "Universal": "Etc/UTC",
    "US/Alaska": "America/Anchorage",
    "US/Aleutian": "America/Adak",
    "US/Arizona": "America/Phoenix",
    "US/Central": "America/Chicago",
    "US/Eastern": "America/New_York",
    "US/East-Indiana": "America/Indiana/Indianapolis",
    "US/Hawaii": "Pacific/Honolulu",
    "US/Indiana-Starke": "America/Indiana/Knox",
    "US/Michigan": "America/Detroit",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "US/Samoa": "Pacific/Pago_Pago",
    "W-SU": "Europe/Moscow",
    "WET": "Europe/Lisbon",
    "Zulu": "Etc/UTC",
}

_NOT_ZONE_NAMES = frozenset({"localtime", "Factory", "posixrules"})

_timezone_cache: dict[str, ZoneInfo] = {}


def timezone(name: str) -> ZoneInfo:
    if name in _timezone_cache:
        return _timezone_cache[name]

    if name.upper() == "UTC":
        tz = ZoneInfo("UTC")
        _timezone_cache[name] = tz
        return tz

    if name in _NOT_ZONE_NAMES:
        raise ZoneInfoNotFoundError(f"Unknown timezone: {name!r}")

    try:
        tz = ZoneInfo(name)
    except KeyError, ValueError:
        canonical_name = TIMEZONE_ALIASES.get(name)
        if canonical_name is None:
            raise ZoneInfoNotFoundError(f"Unknown timezone: {name!r}") from None
        try:
            tz = ZoneInfo(canonical_name)
        except KeyError:
            raise ZoneInfoNotFoundError(f"Unknown timezone: {name!r}") from None

    _timezone_cache[name] = tz
    return tz


def localize_standard(dt: datetime, tz: tzinfo) -> datetime:
    if dt.tzinfo is not None:
        raise ValueError(f"Cannot localize a datetime that already has tzinfo: {dt}")
    first = dt.replace(tzinfo=tz)
    second = dt.replace(tzinfo=tz, fold=1)
    if first.utcoffset() == second.utcoffset():
        return first
    if first.astimezone(UTC).astimezone(tz).replace(tzinfo=None) == dt:
        standard = [instant for instant in (first, second) if not instant.dst()]
        return standard[0] if len(standard) == 1 else second
    return first


def wall_to_utc(dt: datetime, tz: tzinfo) -> datetime:
    return localize_standard(dt, tz).astimezone(UTC).replace(tzinfo=None)


def _utc_to_wall(instant: datetime, tz: tzinfo) -> datetime:
    return instant.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)


def _utc_offset(instant: datetime, tz: tzinfo) -> timedelta | None:
    return instant.replace(tzinfo=UTC).astimezone(tz).utcoffset()


def _offset_change(earlier: datetime, later: datetime, tz: tzinfo) -> datetime:
    target = _utc_offset(later, tz)
    low, high = 0, int((later - earlier).total_seconds())
    while high - low > 1:
        middle = (low + high) // 2
        if _utc_offset(earlier + timedelta(seconds=middle), tz) == target:
            high = middle
        else:
            low = middle
    return earlier + timedelta(seconds=high)


_FIRST_INSTANT = datetime.min.replace(tzinfo=UTC).replace(tzinfo=None)
_LAST_INSTANT = datetime.max.replace(tzinfo=UTC).replace(tzinfo=None)


def _wall_to_utc_within_range(wall: datetime, fold: int, tz: tzinfo) -> datetime:
    try:
        return wall.replace(tzinfo=tz, fold=fold).astimezone(UTC).replace(tzinfo=None)
    except OverflowError:
        return _FIRST_INSTANT if wall.year == 1 else _LAST_INSTANT


def wall_range_to_utc(
    start: datetime, end: datetime | None, tz: tzinfo
) -> list[tuple[datetime, datetime | None]]:
    if start.tzinfo is not None or (end is not None and end.tzinfo is not None):
        raise ValueError(f"Cannot localize a range with tzinfo: {start}, {end}")
    if end is None:
        first = min(_wall_to_utc_within_range(start, fold, tz) for fold in (0, 1))
        if first == _LAST_INSTANT:
            return [(first, first)]
        return [(first, None)]
    points: set[datetime] = set()
    for wall in (start, end):
        earlier, later = sorted(
            _wall_to_utc_within_range(wall, fold, tz) for fold in (0, 1)
        )
        points.update((earlier, later))
        if earlier != later and _utc_offset(earlier, tz) != _utc_offset(later, tz):
            points.add(_offset_change(earlier, later, tz))
    ordered = sorted(points)
    spans: list[tuple[datetime, datetime | None]] = []
    for low, high in itertools.pairwise(ordered):
        try:
            inside = start <= _utc_to_wall(low, tz) < end
        except OverflowError:
            inside = low == _FIRST_INSTANT
        if not inside:
            continue
        if spans and spans[-1][1] == low:
            spans[-1] = (spans[-1][0], high)
        else:
            spans.append((low, high))
    if spans and spans[-1][1] == _LAST_INSTANT:
        spans[-1] = (spans[-1][0], None)
    return spans or [(ordered[0], ordered[0])]


@functools.cache
def all_timezones() -> frozenset[str]:
    return frozenset(available_timezones() - _NOT_ZONE_NAMES)


@functools.cache
def country_timezones() -> Mapping[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for line in _zone_table().splitlines():
        if not line or line.startswith("#"):
            continue
        code, _coordinates, zone = line.split("\t", 3)[:3]
        grouped.setdefault(code, []).append(zone)
    return MappingProxyType({code: tuple(zones) for code, zones in grouped.items()})


def _zone_table() -> str:
    for directory in TZPATH:
        table = Path(directory, "zone.tab")
        if table.is_file():
            return table.read_text(encoding="utf-8")
    try:
        return files("tzdata.zoneinfo").joinpath("zone.tab").read_text(encoding="utf-8")
    except ModuleNotFoundError:
        return ""
