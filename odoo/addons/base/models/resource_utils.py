from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple

from odoo.fields import Domain
from odoo.libs.datetime import elapsed_hours
from odoo.libs.intervals import Intervals
from odoo.tools.date_utils import get_intervals_hours, localized

if TYPE_CHECKING:
    from .resource_resource import ResourceResource

CUSTODY_SYNC = "custody_sync"
CUSTODY_SILENT = "custody_silent"
SKIP_IDENTITY_CHECK = "skip_asset_identity_check"
ASSET_INITIAL_STATE = "draft"
KIND_MODEL_CREATING = "resource_kind_model_creating"
OPERATOR_ROLE = "operator"
MANAGER_ROLE = "manager"
CUSTODIAN_ROLE = "custodian"
EXCLUSIVE_CUSTODY_ROLES = (OPERATOR_ROLE, MANAGER_ROLE)
HOLDING_CUSTODY_ROLES = (OPERATOR_ROLE, CUSTODIAN_ROLE)
CUSTODY_ROLE_BY_FIELD = {"operator_id": OPERATOR_ROLE, "manager_id": MANAGER_ROLE}
DEFAULT_HANDOVER_DELAY = timedelta(days=7)

HOURS_PER_DAY = 8
FULL_ALLOCATION = 100.0


class SlotIntervals(dict):
    __slots__ = ()
    __hash__ = object.__hash__
    __eq__ = object.__eq__
    __ne__ = object.__ne__


def _utc_intervals(intervals: Intervals) -> Intervals:
    return Intervals(
        [
            (localized(start).astimezone(UTC), localized(stop).astimezone(UTC), records)
            for start, stop, records in intervals
        ]
    )


def get_interval_available(
    anchor: datetime,
    duration: timedelta,
    intervals_getter: Callable[[datetime, datetime], tuple[Intervals, Intervals]],
    *,
    iterations: int,
    step: timedelta,
    forward: bool = True,
    blocked: Intervals | None = None,
    earliest: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    if duration <= timedelta(0) or step <= timedelta(0) or iterations < 1:
        raise ValueError("Duration, window step and iteration count must be positive")
    anchor = localized(anchor).astimezone(UTC)
    earliest = localized(earliest).astimezone(UTC) if earliest is not None else None
    if forward and earliest is not None:
        anchor = max(anchor, earliest)
    blocked = _utc_intervals(blocked) if blocked is not None else Intervals()
    remaining, edge = duration, None
    occupied_history = Intervals()
    for index in range(iterations):
        start_window = anchor + step * index if forward else anchor - step * (index + 1)
        stop_window = start_window + step
        if earliest is not None:
            start_window = max(start_window, earliest)
        if start_window >= stop_window:
            return None
        available, occupied = intervals_getter(start_window, stop_window)
        available = _utc_intervals(available)
        occupied_history |= _utc_intervals(occupied)
        for start, stop, records in available if forward else reversed(available):
            edge = edge or (start if forward else stop)
            span = stop - start
            candidate = Intervals(
                [
                    (
                        (edge or start) if forward else stop - min(remaining, span),
                        start + min(remaining, span) if forward else edge,
                        records,
                    )
                ]
            )
            while conflict := next(
                iter(candidate & occupied_history or candidate & blocked), None
            ):
                start, stop = (
                    (max(start, conflict[1]), stop)
                    if forward
                    else (start, min(stop, conflict[0]))
                )
                span = stop - start
                edge = (start if forward else stop) if span else None
                remaining = duration
                candidate = Intervals(
                    [
                        (
                            (edge or start) if forward else stop - min(remaining, span),
                            start + min(remaining, span) if forward else edge or stop,
                            records,
                        )
                    ]
                )
            if span >= remaining:
                found = (
                    (edge, start + remaining) if forward else (stop - remaining, edge)
                )
                return tuple(moment.replace(microsecond=0) for moment in found)
            remaining -= span
        if not forward and earliest is not None and start_window <= earliest:
            break
    return None


class FirstServedClaim(NamedTuple):
    key: Any
    resource: Any
    start: datetime
    stop: datetime
    percentage: float
    order_id: int | None
    consumes: bool


def changed_vals(record, vals: dict[str, Any]) -> dict[str, Any]:
    record.check_singleton()
    return {
        fname: value
        for fname, value in vals.items()
        if record._fields[fname].convert_to_write(record[fname], record) != value
    }


def last_day_of(start: datetime, stop: datetime) -> date:
    if stop > start:
        stop -= timedelta(microseconds=1)
    return stop.date()


def split_at_midnight(
    intervals: Iterable[tuple[datetime, datetime, Any]],
) -> Iterator[tuple[datetime, datetime, Any]]:
    for start, stop, meta in intervals:
        while start < stop:
            midnight = datetime.combine(
                start.date() + timedelta(days=1), time.min, start.tzinfo
            )
            piece_stop = min(stop, midnight)
            yield start, piece_stop, meta
            start = piece_stop


def hours_by_day(
    intervals: Iterable[tuple[datetime, datetime, Any]],
) -> defaultdict[date, float]:
    hours: defaultdict[date, float] = defaultdict(float)
    for start, stop, _meta in split_at_midnight(intervals):
        hours[start.date()] += elapsed_hours(start, stop)
    return hours


def week_type_of(day: date) -> str:
    return str((day.toordinal() - 1) // 7 % 2)


def week_of(day: date, week_start: int) -> date:
    return day - timedelta(days=(day.weekday() - week_start) % 7)


def get_work_hours_by_date(
    first_day: date,
    hours_per_day: float,
    hours_per_week: float,
    leave_hours: Mapping[date, float],
) -> dict[date, float]:
    remaining = hours_per_week
    filled = {}
    for offset in range(7):
        day = first_day + timedelta(days=offset)
        leave = min(hours_per_day, leave_hours.get(day, 0.0))
        remaining -= min(leave, remaining)
        work = max(0.0, min(hours_per_day - leave, remaining))
        remaining -= work
        filled[day] = work
    return filled


def capacity_timeline(bookings, start, stop):
    if stop <= start:
        return
    changes = defaultdict(float, {start: 0.0, stop: 0.0})
    for booking_start, booking_stop, load in bookings:
        left, right = max(start, booking_start), min(stop, booking_stop)
        if left < right and load > 0:
            changes[left] += load
            changes[right] -= load
    previous, total = start, 0.0
    for instant, change in sorted(changes.items()):
        if previous < instant:
            yield previous, instant, total
        total += change
        previous = instant


def saturated_spans(bookings, start, stop, ceiling, demand=FULL_ALLOCATION):
    for left, right, load in capacity_timeline(bookings, start, stop):
        load = round(load, 9)
        if load > 0 and load + demand > ceiling + 1e-7:
            yield left, right


def peak_capacity(bookings, start, stop):
    return max(
        (load for _, _, load in capacity_timeline(bookings, start, stop)), default=0.0
    )


def peak_capacities(bookings, windows):
    spans = [(start, stop) for start, stop in windows if start < stop]
    if not spans:
        return [0.0] * len(windows)
    timeline = list(
        capacity_timeline(
            bookings, min(start for start, _ in spans), max(stop for _, stop in spans)
        )
    )
    lefts = [left for left, _right, _total in timeline]
    peaks = []
    for start, stop in windows:
        peak = 0.0
        if start < stop:
            index = bisect_right(lefts, start) - 1
            while index < len(timeline) and timeline[index][0] < stop:
                peak = max(peak, round(timeline[index][2], 9))
                index += 1
        peaks.append(peak)
    return peaks


def filter_domain_leaf(
    domain: Domain | list,
    field_check: Callable[[str], bool],
    field_name_mapping: dict[str, str] | None = None,
) -> Domain:
    field_name_mapping = field_name_mapping or {}

    def adapt_condition(condition, ignored):
        field_name = condition.field_expr
        if not field_check(field_name):
            return ignored
        field_name = field_name_mapping.get(field_name)
        if field_name is None:
            return condition
        return Domain(field_name, condition.operator, condition.value)

    def adapt_domain(domain: Domain, ignored) -> Domain:
        if hasattr(domain, "OPERATOR"):
            if domain.OPERATOR in ("&", "|"):
                domain = domain.apply(
                    adapt_domain(d, domain.ZERO) for d in domain.children
                )
            elif domain.OPERATOR == "!":
                domain = ~adapt_domain(~domain, ~ignored)
            else:
                msg = f"domain.OPERATOR = {domain.OPERATOR!r} unhandled"
                raise AssertionError(msg)
        else:
            domain = domain.map_conditions(
                lambda condition: adapt_condition(condition, ignored)
            )
        return ignored if domain.is_true() or domain.is_false() else domain

    domain = Domain(domain)
    if domain.is_false():
        return domain
    return adapt_domain(domain, ignored=Domain.TRUE)


@dataclass
class ResourceSchedule:
    intervals: defaultdict[int, Intervals] = field(
        default_factory=lambda: defaultdict(Intervals)
    )
    calendar_intervals: dict[int, Intervals] = field(default_factory=dict)
    hours_per_day: defaultdict[int, dict] = field(
        default_factory=lambda: defaultdict(dict)
    )
    hours_per_week: defaultdict[int, dict] = field(
        default_factory=lambda: defaultdict(dict)
    )
    flexible_ids: frozenset[int] = frozenset()

    def work_hours(
        self,
        resource: ResourceResource,
        intervals: Intervals | None = None,
        work_hours_per_day: dict[Any, float] | None = None,
    ) -> float:
        if intervals is None:
            intervals = self.intervals[resource.id]
        if resource.id in self.flexible_ids:
            return resource._get_flexible_resource_work_hours(
                intervals,
                self.hours_per_day[resource.id],
                self.hours_per_week[resource.id],
                work_hours_per_day,
            )
        hours = get_intervals_hours(intervals)
        if work_hours_per_day is not None:
            for day, day_hours in hours_by_day(intervals).items():
                work_hours_per_day[day] += day_hours
        return hours
