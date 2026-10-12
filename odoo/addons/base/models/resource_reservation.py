import logging
import operator as operator_module
from collections import defaultdict
from datetime import UTC
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.datetime import timezone
from odoo.libs.intervals import Intervals
from odoo.tools import SQL
from odoo.tools.date_utils import get_intervals_hours, localized

from .resource_utils import (
    FirstServedClaim,
    hours_by_day,
    peak_capacities,
    saturated_spans,
)

_logger = logging.getLogger(__name__)

_CONFLICT_COUNT = {
    "=": lambda count, value: SQL("%s = %s", count, value),
    "!=": lambda count, value: SQL("%s != %s", count, value),
    "<": lambda count, value: SQL("%s < %s", count, value),
    "<=": lambda count, value: SQL("%s <= %s", count, value),
    ">": lambda count, value: SQL("%s > %s", count, value),
    ">=": lambda count, value: SQL("%s >= %s", count, value),
}

COMPARATORS = {
    "=": operator_module.eq,
    "!=": operator_module.ne,
    "<": operator_module.lt,
    "<=": operator_module.le,
    ">": operator_module.gt,
    ">=": operator_module.ge,
}


def _solve_percentage(hours_at, wanted: float) -> float:
    if wanted <= 0:
        return 0.0
    full = hours_at(100.0)
    if not full:
        return 100.0
    low, high = 0.0, 100.0
    while hours_at(high) < wanted:
        if high >= 100.0 * 2**10 or hours_at(high * 2) <= hours_at(high):
            return 100.0 * wanted / full
        low, high = high, high * 2
    for _step in range(50):
        middle = (low + high) / 2
        if hours_at(middle) < wanted:
            low = middle
        else:
            high = middle
    return high


class ResourceReservation(models.Model):
    _name = "resource.reservation"
    _description = "Resource Reservation"
    _inherit = ["mixin.resource.scheduling.tools", "mixin.resource.ledger"]
    _order = "date_start"
    _check_company_auto = True

    _OVERLAP_SWEEP_FIELDS = [
        "date_start",
        "date_end",
        "resource_id",
        "allocated_percentage",
        "active",
    ]

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        precompute=True,
        store=True,
        index="btree_not_null",
        readonly=False,
    )

    date_start = fields.Datetime(
        string="Scheduled Start",
        index=True,
    )
    date_end = fields.Datetime(
        string="Scheduled End",
        index=True,
    )

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        ondelete="restrict",
        check_company=True,
        help="The resource (person, equipment) assigned to this schedule.",
    )
    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Working Calendar",
        compute="_compute_resource_calendar_id",
        store=True,
        readonly=False,
        check_company=True,
    )

    allocated_hours = fields.Float(
        compute="_compute_allocated_hours",
        store=True,
        readonly=False,
        help="Working hours between start and end, respecting the resource calendar.",
    )
    allocated_percentage = fields.Float(
        string="Allocation %",
        default=100.0,
        help="Percentage of the resource's work capacity allocated to this schedule.",
    )
    _check_allocated_percentage = models.Constraint(
        "CHECK(allocated_percentage IS NOT NULL"
        " AND allocated_percentage >= 0 AND allocated_percentage < 'Infinity'::float8)",
        "Allocation % must be finite and nonnegative.",
    )

    schedule_overlap_count = fields.Integer(
        string="Scheduling Conflicts",
        compute="_compute_schedule_overlap_count",
        search="_search_schedule_overlap_count",
    )

    peak_booking_percentage = fields.Float(
        string="Peak Booking %",
        compute="_compute_booking_load",
    )
    booking_state = fields.Selection(
        selection=[
            ("under", "Underbooked"),
            ("full", "Fully Booked"),
            ("over", "Overbooked"),
            ("exceeded", "Ceiling Exceeded"),
        ],
        string="Booking Status",
        compute="_compute_booking_load",
    )

    res_model = fields.Char(
        string="Source Model",
        index=True,
        readonly=True,
        help="Technical name of the model that created this reservation.",
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Source Record",
        index=True,
        readonly=True,
        help="ID of the record in the source model.",
    )

    enforcement_mode = fields.Selection(
        selection=[("soft", "Warning"), ("hard", "Block")],
        default="soft",
        required=True,
        help="Warning permits excess capacity unless the resource enforces its ceiling. Block prevents total simultaneous allocation from exceeding the resource ceiling.",
    )

    origin_display = fields.Char(
        string="Source",
        compute="_compute_origin_display",
    )

    _resource_schedule_idx = models.Index("(resource_id, date_start, date_end)")
    _origin_idx = models.Index("(res_model, res_id)")

    @api.constrains("date_start", "date_end")
    def _check_date_sanity(self) -> None:
        for record in self:
            if (
                record.date_start
                and record.date_end
                and record.date_start > record.date_end
            ):
                raise ValidationError(
                    self.env._(
                        "%(name)s: start date must be before end date.",
                        name=record.name,
                    )
                )

    @api.constrains(
        "date_start",
        "date_end",
        "resource_id",
        "allocated_percentage",
        "active",
        "enforcement_mode",
    )
    def _check_hard_overlap(self) -> None:
        live = self.filtered(
            lambda r: (
                r.active
                and r.resource_id
                and r.date_start
                and r.date_end
                and r.date_start < r.date_end
                and r.allocated_percentage > 0
            )
        )
        hard = live.filtered_domain(self._get_domain_enforced_booking())

        if live:
            live.resource_id._lock_for_integrity()
            windows_by_resource = defaultdict(lambda: [None, None])
            for record in live:
                window = windows_by_resource[record.resource_id.id]
                window[0] = (
                    record.date_start
                    if window[0] is None
                    else min(window[0], record.date_start)
                )
                window[1] = (
                    record.date_end
                    if window[1] is None
                    else max(window[1], record.date_end)
                )
            hard |= (
                self.sudo()
                .search(
                    Domain.AND(
                        [
                            Domain("id", "not in", live.ids),
                            self._get_domain_enforced_booking(),
                            Domain.OR(
                                self._get_domain_occupancy(
                                    self.env["resource.resource"].browse(resource_id),
                                    since=start,
                                    until=end,
                                )
                                for resource_id, (
                                    start,
                                    end,
                                ) in windows_by_resource.items()
                            ),
                        ]
                    )
                )
                .with_env(self.env)
            )
        if not hard:
            return
        hard._compute_booking_load()
        for record in hard:
            if (
                record.peak_booking_percentage
                > record.resource_id.booking_limit_percentage + 1e-7
            ):
                raise ValidationError(
                    self.env._(
                        "%(name)s: %(resource)s exceeds its configured booking ceiling during this time.",
                        name=record.name,
                        resource=record.resource_id.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.invalidate_model(
            ["peak_booking_percentage", "booking_state", "schedule_overlap_count"]
        )
        records._recompute_first_served_neighbours()
        return records

    def write(self, vals):
        if set(vals) & set(self._OVERLAP_SWEEP_FIELDS):
            resources = self.resource_id
            if vals.get("resource_id"):
                resources |= self.env["resource.resource"].browse(vals["resource_id"])
            resources._lock_for_integrity()
        moves = set(vals) & set(self._OVERLAP_SWEEP_FIELDS)
        before = self._get_domain_first_served_neighbours() if moves else None
        result = super().write(vals)
        self.invalidate_model(
            ["peak_booking_percentage", "booking_state", "schedule_overlap_count"]
        )
        if moves:
            self._recompute_first_served_neighbours(before)
        return result

    def unlink(self):
        self.resource_id._lock_for_integrity()
        neighbours = self._get_domain_first_served_neighbours()
        result = super().unlink()
        self.browse()._recompute_first_served_neighbours(neighbours)
        self.invalidate_model(
            ["peak_booking_percentage", "booking_state", "schedule_overlap_count"]
        )
        return result

    @api.depends("resource_id.company_id")
    def _compute_company_id(self):
        for record in self:
            record.company_id = (
                record.resource_id.company_id or record.company_id or self.env.company
            )

    @api.depends(
        "resource_id",
        "resource_id.booking_limit_percentage",
        "date_start",
        "date_end",
        "allocated_percentage",
        "active",
    )
    def _compute_booking_load(self) -> None:
        dated = self.filtered(
            lambda r: r.active and r.resource_id and r.date_start and r.date_end
        )
        loads = {}
        if dated:
            stored_ids = [record._origin.id for record in dated if record._origin.id]
            loads = self._get_booking_load_batch(
                dated.resource_id,
                min(dated.mapped("date_start")),
                max(dated.mapped("date_end")),
                domain=[("id", "not in", stored_ids)],
            )
            for record in dated.filtered(
                lambda r: r.date_start < r.date_end and r.allocated_percentage > 0
            ):
                loads[record.resource_id.id].append(
                    (record.date_start, record.date_end, record.allocated_percentage)
                )
        peaks = {}
        for resource_id, records in dated.grouped(lambda r: r.resource_id.id).items():
            windows = [(record.date_start, record.date_end) for record in records]
            peaks.update(
                zip(records, peak_capacities(loads[resource_id], windows), strict=True)
            )
        for record in self:
            peak = peaks.get(record, 0.0)
            record.peak_booking_percentage = peak
            if peak > record.resource_id.booking_limit_percentage + 1e-7:
                record.booking_state = "exceeded"
            elif peak > 100 + 1e-7:
                record.booking_state = "over"
            elif peak >= 100 - 1e-7:
                record.booking_state = "full"
            else:
                record.booking_state = "under"

    @api.depends("resource_id", "company_id")
    def _compute_resource_calendar_id(self) -> None:
        for record in self:
            calendar = record.resource_id.calendar_id
            company = record.company_id or record.env.company
            if calendar and calendar.company_id and calendar.company_id != company:
                calendar = calendar.browse()
            record.resource_calendar_id = calendar or company.resource_calendar_id

    @api.depends(
        "date_start",
        "date_end",
        "resource_id",
        "resource_calendar_id",
        "allocated_percentage",
    )
    def _compute_allocated_hours(self) -> None:
        undated = self.filtered(lambda r: not r.date_start or not r.date_end)
        undated.allocated_hours = 0.0
        dated = self - undated
        if not dated:
            return

        flexible = dated.filtered(
            lambda r: r.resource_id and r.resource_id._is_flexible()
        )
        imposed = flexible.filtered(
            lambda r: (
                r.resource_calendar_id
                and r.resource_calendar_id != r.resource_id.calendar_id
            )
        )
        for record in imposed:
            record.allocated_hours = record._scale_allocation(
                record._scheduling_get_work_hours(
                    record.date_start,
                    record.date_end,
                    resource=record.resource_id,
                    calendar=record.resource_calendar_id,
                )
            )
        own = (flexible - imposed).filtered(lambda r: r.date_start < r.date_end)
        (flexible - imposed - own).allocated_hours = 0.0
        budgeted = own.filtered(lambda r: not r.resource_id._is_fully_flexible())
        for record, hours in budgeted._get_first_served_hours().items():
            record.allocated_hours = hours
        own -= budgeted
        if own:
            schedule = own.resource_id._get_work_schedule(
                localized(min(own.mapped("date_start"))),
                localized(max(own.mapped("date_end"))),
            )
            no_attendance = self.env["resource.calendar.attendance"]
            for record in own:
                window = Intervals(
                    [
                        (
                            localized(record.date_start),
                            localized(record.date_end),
                            no_attendance,
                        )
                    ]
                )
                record.allocated_hours = record._scale_allocation(
                    schedule.work_hours(
                        record.resource_id,
                        schedule.intervals[record.resource_id.id] & window,
                    )
                )

        groups = defaultdict(self.browse)
        for record in dated - flexible:
            groups[record.resource_calendar_id] |= record

        attendance = self.env["resource.calendar.attendance"]
        for calendar, records in groups.items():
            window_start = localized(min(records.mapped("date_start")))
            window_end = localized(max(records.mapped("date_end")))

            if calendar:
                native = records.resource_id.filtered_domain(
                    [("calendar_id", "=", calendar.id)]
                )
            else:
                native = records.resource_id
            overridden = records.resource_id - native
            intervals_per_resource = {}
            if native:
                intervals_per_resource, _calendar_intervals = (
                    native._get_valid_work_intervals(window_start, window_end)
                )
            if overridden and calendar:
                intervals_per_resource.update(
                    calendar._work_intervals_batch(
                        window_start, window_end, resources=overridden
                    )
                )
            calendar_intervals = None
            if len(records.filtered(lambda r: not r.resource_id)) and calendar:
                calendar_intervals = calendar._work_intervals_batch(
                    window_start, window_end
                )[False]

            for record in records:
                if record.resource_id:
                    intervals = intervals_per_resource.get(record.resource_id.id)
                elif calendar_intervals is not None:
                    intervals = calendar_intervals
                else:
                    span = localized(record.date_end) - localized(record.date_start)
                    record.allocated_hours = record._scale_allocation(
                        span.total_seconds() / 3600.0
                    )
                    continue
                clipped = (intervals or Intervals()) & Intervals(
                    [
                        (
                            localized(record.date_start),
                            localized(record.date_end),
                            attendance,
                        )
                    ]
                )
                record.allocated_hours = record._scale_allocation(
                    get_intervals_hours(clipped)
                )

    def _get_first_served_hours(self) -> dict:
        return self._get_first_served_hours_of(
            [
                FirstServedClaim(
                    key=record,
                    resource=record.resource_id,
                    start=record.date_start,
                    stop=record.date_end,
                    percentage=record.allocated_percentage,
                    order_id=record._origin.id or None,
                    consumes=record.active,
                )
                for record in self
            ],
            ignore_ids=[record._origin.id for record in self if record._origin.id],
        )

    @api.model
    def _get_first_served_hours_of(self, claims, ignore_ids=()) -> dict:
        return self._walk_first_served(claims, ignore_ids)[0]

    @api.model
    def _get_first_served_percentages_of(self, claims, hours, ignore_ids=()) -> dict:
        return self._walk_first_served(claims, ignore_ids, hours)[1]

    @api.model
    def _get_first_served_days_of(self, claims, ignore_ids=()) -> dict:
        return self._walk_first_served(claims, ignore_ids)[2]

    @api.model
    def _walk_first_served(self, claims, ignore_ids=(), wanted=None) -> tuple:
        wanted = wanted or {}
        if not claims:
            return {}, {}, {}
        resources = self.env["resource.resource"].union(
            *(claim.resource for claim in claims)
        )
        start, stop = resources._get_flexible_week_bounds(
            localized(min(claim.start for claim in claims)),
            localized(max(claim.stop for claim in claims)),
        )
        schedule = resources._get_work_schedule(start, stop)
        others = self._get_occupancy(
            resources, start, stop, [("id", "not in", list(ignore_ids))]
        )
        queue = defaultdict(list)
        for other in others:
            queue[other.resource_id.id].append(
                (
                    other.date_start,
                    other.id,
                    0,
                    FirstServedClaim(
                        key=None,
                        resource=other.resource_id,
                        start=other.date_start,
                        stop=other.date_end,
                        percentage=other.allocated_percentage,
                        order_id=other.id,
                        consumes=True,
                    ),
                )
            )
        for sequence, claim in enumerate(claims, start=1):
            queue[claim.resource.id].append(
                (claim.start, claim.order_id or float("inf"), sequence, claim)
            )
        no_attendance = self.env["resource.calendar.attendance"]
        hours_by_key, percentages, days_by_key = {}, {}, {}
        for resource in resources:
            tz = timezone(resource.tz)
            day_capacity = schedule.hours_per_day[resource.id]
            day_left = dict(day_capacity)
            week_left = dict(schedule.hours_per_week[resource.id])
            for *_order, claim in sorted(
                queue[resource.id], key=operator_module.itemgetter(0, 1, 2)
            ):
                window = Intervals(
                    [
                        (
                            localized(claim.start).astimezone(tz),
                            localized(claim.stop).astimezone(tz),
                            no_attendance,
                        )
                    ]
                )
                reach = []
                alone_week_left = dict(schedule.hours_per_week[resource.id])
                for day, hours in sorted(
                    hours_by_day(schedule.intervals[resource.id] & window).items()
                ):
                    week = resource._get_week_of(day)
                    alone = max(
                        0.0,
                        min(
                            hours,
                            day_capacity.get(day, 0.0),
                            alone_week_left.get(week, 0.0),
                        ),
                    )
                    alone_week_left[week] = alone_week_left.get(week, 0.0) - alone
                    reach.append((day, week, alone))

                def grants(
                    percentage, reach=reach, day_left=day_left, week_left=week_left
                ):
                    taken = defaultdict(float)
                    for day, week, hours in reach:
                        grant = max(
                            0.0,
                            min(
                                hours * percentage / 100.0,
                                day_left.get(day, 0.0),
                                week_left.get(week, 0.0) - taken[week],
                            ),
                        )
                        taken[week] += grant
                        yield day, week, grant

                percentage = claim.percentage
                if claim.key in wanted:
                    percentage = _solve_percentage(
                        lambda p, grants=grants: sum(g for *_, g in grants(p)),
                        wanted[claim.key],
                    )
                    percentages[claim.key] = percentage
                granted = 0.0
                by_day = {}
                for day, week, grant in list(grants(percentage)):
                    if claim.consumes:
                        day_left[day] = day_left.get(day, 0.0) - grant
                        week_left[week] = week_left.get(week, 0.0) - grant
                    granted += grant
                    by_day[day] = grant
                if claim.key is not None:
                    hours_by_key[claim.key] = round(granted, 2)
                    days_by_key[claim.key] = by_day
        return hours_by_key, percentages, days_by_key

    def _get_domain_first_served_neighbours(self) -> Domain:
        budgeted = self.filtered(
            lambda r: (
                r.resource_id
                and r.date_start
                and r.date_end
                and r.resource_id._is_flexible()
                and not r.resource_id._is_fully_flexible()
            )
        )
        if not budgeted:
            return Domain.FALSE
        start, stop = budgeted.resource_id._get_flexible_week_bounds(
            localized(min(budgeted.mapped("date_start"))),
            localized(max(budgeted.mapped("date_end"))),
        )
        return self._get_domain_occupancy(
            budgeted.resource_id, since=start, until=stop
        ) & Domain("id", "not in", self.ids)

    def _recompute_first_served_neighbours(self, domain=Domain.FALSE) -> None:
        domain |= self._get_domain_first_served_neighbours()
        if domain.is_false():
            return
        neighbours = self._recompute_reservations_field(domain, "allocated_hours")
        Scheduling = self.env.registry["mixin.resource.scheduling"]
        for model_name, owned in neighbours.grouped("res_model").items():
            owners = self.env.get(model_name)
            if isinstance(owners, Scheduling):
                owners.browse(
                    owned.mapped("res_id")
                ).exists()._recompute_first_served_hours()

    @api.depends(
        "date_start", "date_end", "resource_id", "allocated_percentage", "active"
    )
    def _compute_schedule_overlap_count(self) -> None:
        conflicts = self._get_conflicting_reservations()
        for record in self:
            record.schedule_overlap_count = len(conflicts[record.id])

    @api.depends("res_model", "res_id")
    def _compute_origin_display(self) -> None:
        self.origin_display = False
        with_origin = self.filtered(lambda r: r.res_model and r.res_id)
        for model_name, records in with_origin.grouped("res_model").items():
            if model_name not in self.env:
                for record in records:
                    record.origin_display = f"{model_name},{record.res_id}"
                continue
            sources = (
                self.env[model_name]
                .browse(records.mapped("res_id"))
                .exists()
                ._filtered_access("read")
            )
            names = dict(zip(sources.ids, sources.mapped("display_name"), strict=True))
            for record in records:
                record.origin_display = names.get(record.res_id) or (
                    f"{model_name},{record.res_id}"
                )

    @api.model
    def _recompute_allocated_hours(self, domain) -> None:
        self._recompute_reservations_field(domain, "allocated_hours")

    def _recompute_reservations_field(self, domain, fname) -> Self:
        reservations = self.sudo().with_context(active_test=False).search(domain)
        if reservations:
            self.env.add_to_compute(self._fields[fname], reservations)
            reservations.modified([fname])
        return reservations

    def _scale_allocation(self, work_hours):
        self.check_singleton()
        return round(work_hours * self.allocated_percentage / 100.0, 2)

    @api.model
    def _get_domain_enforced_booking(self):
        return Domain.OR(
            [
                Domain("enforcement_mode", "=", "hard"),
                Domain("resource_id.enforce_booking_limit", "=", True),
            ]
        )

    @api.model
    def _get_domain_occupancy(self, resources, *, since=None, until=None):
        since = (
            localized(fields.Datetime.to_datetime(since))
            .astimezone(UTC)
            .replace(tzinfo=None)
            if since
            else None
        )
        until = (
            localized(fields.Datetime.to_datetime(until))
            .astimezone(UTC)
            .replace(tzinfo=None)
            if until
            else None
        )
        if since is not None and until is not None and until <= since:
            return Domain.FALSE
        domain = Domain(
            [
                ("resource_id", "in", resources.ids),
                ("active", "=", True),
                ("allocated_percentage", ">", 0),
            ]
        )
        domain &= Domain.custom(
            to_sql=lambda model, alias, query: SQL(
                "%s > %s",
                model._field_to_sql(alias, "date_end", query),
                model._field_to_sql(alias, "date_start", query),
            )
        )
        if since is not None:
            domain &= Domain("date_end", ">", since)
        if until is not None:
            domain &= Domain("date_start", "<", until)
        return domain

    @api.model
    def _get_occupancy(self, resources, start, stop, domain=None):
        return self.sudo().search_fetch(
            self._get_domain_occupancy(resources, since=start, until=stop)
            & Domain(domain or []),
            [
                "resource_id",
                "date_start",
                "date_end",
                "allocated_percentage",
                "enforcement_mode",
            ],
        )

    @api.model
    def _get_booking_load_batch(self, resources, start, stop, domain=None):
        bookings = self._get_occupancy(resources, start, stop, domain)
        result = {resource.id: [] for resource in resources}
        for booking in bookings:
            result[booking.resource_id.id].append(
                (
                    booking.date_start,
                    booking.date_end,
                    booking.allocated_percentage,
                )
            )
        return result

    def _get_conflicting_reservations(self):
        stored = self.filtered(
            lambda r: (
                r.id
                and isinstance(r.id, int)
                and r.resource_id
                and r.date_start
                and r.date_end
            )
        )
        empty = self.browse()
        result = dict.fromkeys(self._ids, empty)
        if not stored:
            return result

        self.flush_model(self._OVERLAP_SWEEP_FIELDS)
        partners = self._get_overlap_partners(
            (
                SQL("AND resource_id = ANY(%s)", list(set(stored.resource_id.ids))),
                SQL("AND date_start < %s", max(stored.mapped("date_end"))),
                SQL("AND date_end > %s", min(stored.mapped("date_start"))),
            )
        )
        for record in stored:
            result[record.id] = self.browse(sorted(partners.get(record.id, ())))
        return result

    @api.model
    def _get_prospective_conflicts(self, vals_list, ignore_ids=()) -> Self:
        prospective = []
        for index, vals in enumerate(vals_list):
            resource_id = vals.get("resource_id")
            date_start, date_end = vals.get("date_start"), vals.get("date_end")
            if not resource_id or not date_start or not date_end:
                continue
            date_start = fields.Datetime.to_datetime(date_start)
            date_end = fields.Datetime.to_datetime(date_end)
            if date_end <= date_start:
                continue
            pct = vals.get("allocated_percentage")
            pct = 100.0 if pct is None else pct
            if pct <= 0:
                continue
            prospective.append((-(index + 1), resource_id, date_start, date_end, pct))
        if not prospective:
            return self.browse()

        self.flush_model(self._OVERLAP_SWEEP_FIELDS)
        conditions = [
            SQL("AND resource_id = ANY(%s)", list({row[1] for row in prospective})),
            SQL("AND date_start < %s", max(row[3] for row in prospective)),
            SQL("AND date_end > %s", min(row[2] for row in prospective)),
        ]
        if ignore_ids:
            conditions.append(SQL("AND id != ALL(%s)", list(ignore_ids)))
        partners = self._get_overlap_partners(tuple(conditions), prospective)
        conflicting = set()
        for sentinel, *_rest in prospective:
            conflicting.update(peer for peer in partners.get(sentinel, ()) if peer > 0)
        return self.browse(sorted(conflicting))

    @api.model
    def _search_schedule_overlap_count(self, operator, value):
        if operator not in _CONFLICT_COUNT or not isinstance(value, int):
            return NotImplemented
        value = int(value)
        self.flush_model(self._OVERLAP_SWEEP_FIELDS)
        matches = _CONFLICT_COUNT[operator](SQL("cardinality(peers)"), value)
        zero_matches = COMPARATORS[operator](0, value)

        def to_sql(model, alias, query):
            return SQL(
                "%s %s (SELECT id FROM (%s) AS partners(id, peers) WHERE %s)",
                model._field_to_sql(alias, "id", query),
                SQL("NOT IN") if zero_matches else SQL("IN"),
                model._get_sql_overlap_partners(),
                SQL("NOT (%s)", matches) if zero_matches else matches,
            )

        return Domain.custom(to_sql=to_sql)

    def _get_overlap_partners(self, extra_conditions=(), prospective=()) -> dict:
        self.env.cr.execute(
            self._get_sql_overlap_partners(extra_conditions, prospective)
        )
        return {res_id: set(peers) for res_id, peers in self.env.cr.fetchall()}

    def _get_sql_overlap_partners(self, extra_conditions=(), prospective=()) -> SQL:
        rows = SQL(
            """
            SELECT id, resource_id, date_start, date_end,
                   GREATEST(0, COALESCE(allocated_percentage, 100))::float8
              FROM %s
             WHERE resource_id IS NOT NULL
               AND active
               AND allocated_percentage > 0
               AND date_start IS NOT NULL
               AND date_end IS NOT NULL
               AND date_end > date_start
               %s
            """,
            SQL.identifier(self._table),
            SQL(" ").join(extra_conditions),
        )
        if prospective:
            rows = SQL(
                "%s UNION ALL SELECT * FROM (VALUES %s)"
                " AS prospective(id, resource_id, date_start, date_end, pct)",
                rows,
                SQL(", ").join(
                    SQL(
                        "(%s::int, %s::int, %s::timestamp, %s::timestamp, %s::float8)",
                        *row,
                    )
                    for row in prospective
                ),
            )
        return SQL(
            """
                WITH booking(id, resource_id, date_start, date_end, pct) AS (%s),
                     event AS (
                         SELECT resource_id, date_start AS instant, 1 AS kind, pct
                           FROM booking
                          UNION ALL
                         SELECT resource_id, date_end, 0, -pct
                           FROM booking
                     ),
                     load AS (
                         SELECT resource_id, instant, kind,
                                SUM(pct) OVER (
                                    PARTITION BY resource_id
                                    ORDER BY instant, kind
                                    ROWS UNBOUNDED PRECEDING
                                ) AS total
                           FROM event
                     ),
                     hot AS (
                         SELECT DISTINCT resource_id, instant
                           FROM load
                          WHERE kind = 1 AND total > 100
                     )
                SELECT this.id, ARRAY_AGG(DISTINCT other.id)
                  FROM hot
                  JOIN booking AS this
                    ON this.resource_id = hot.resource_id
                   AND this.date_start <= hot.instant
                   AND this.date_end > hot.instant
                  JOIN booking AS other
                    ON other.resource_id = hot.resource_id
                   AND other.id <> this.id
                   AND other.date_start <= hot.instant
                   AND other.date_end > hot.instant
                 GROUP BY this.id
                """,
            rows,
        )

    @api.autovacuum
    def _gc_orphan_reservations(self) -> None:
        reservations = self.sudo().with_context(active_test=False)
        model_names = [
            res_model
            for [res_model] in reservations._read_group(
                [("res_model", "!=", False)], groupby=["res_model"]
            )
        ]
        orphan_ids = []
        for model_name in model_names:
            model = self.env.get(model_name)
            if model is None:
                orphan_ids.extend(
                    reservations.search([("res_model", "=", model_name)]).ids
                )
                continue
            if not model._auto:
                continue
            self.env.cr.execute(
                SQL(
                    """
                    SELECT reservation.id
                      FROM %s AS reservation
                 LEFT JOIN %s AS source ON source.id = reservation.res_id
                     WHERE reservation.res_model = %s
                       AND source.id IS NULL
                    """,
                    SQL.identifier(self._table),
                    SQL.identifier(model._table),
                    model_name,
                )
            )
            orphan_ids.extend(row[0] for row in self.env.cr.fetchall())

        if orphan_ids:
            _logger.info(
                "Garbage-collecting %s orphan resource.reservation record(s)",
                len(orphan_ids),
            )
            reservations.browse(orphan_ids).unlink()

    def action_view_origin(self) -> dict | None:
        self.check_singleton()
        if not self.res_model or not self.res_id:
            return None
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [(False, "form")],
            "target": "current",
        }

    @api.model
    def _get_enforced_booking_intervals_batch(
        self, start_dt, end_dt, resources=None, *, reservations_to_ignore=None
    ) -> dict[int | bool, Intervals]:
        result: dict[int | bool, Intervals] = {False: Intervals()}
        if not resources:
            return result
        start = localized(start_dt).astimezone(UTC)
        stop = localized(end_dt).astimezone(UTC)
        bookings = self._get_occupancy(
            resources,
            start,
            stop,
            Domain("id", "not in", reservations_to_ignore._origin.ids)
            if reservations_to_ignore
            else None,
        )
        enforced = bookings.filtered_domain(self._get_domain_enforced_booking())
        by_resource = bookings.grouped("resource_id")
        for resource in resources:
            mine = by_resource.get(resource, bookings.browse())
            held = Intervals(
                [
                    (
                        localized(booking.date_start),
                        localized(booking.date_end),
                        booking,
                    )
                    for booking in mine & enforced
                ]
            )
            if held:
                saturated = saturated_spans(
                    [
                        (
                            localized(booking.date_start),
                            localized(booking.date_end),
                            booking.allocated_percentage,
                        )
                        for booking in mine
                    ],
                    start,
                    stop,
                    mine.resource_id.booking_limit_percentage,
                )
                held &= Intervals(
                    [(left, right, bookings.browse()) for left, right in saturated]
                )
            result[resource.id] = held
        return result

    def _get_reservation_intervals_batch(
        self, start_dt, end_dt, resources, domain=None
    ) -> dict:
        if not resources:
            return {}

        base_domain = self._get_domain_occupancy(
            resources, since=start_dt, until=end_dt
        ) & Domain(domain or [])

        tuples_by_resource = defaultdict(list)
        for res in self.sudo().search(base_domain):
            tuples_by_resource[res.resource_id.id].append(
                (localized(res.date_start), localized(res.date_end), res)
            )

        return {
            resource.id: Intervals(tuples_by_resource.get(resource.id, []))
            for resource in resources
        }
