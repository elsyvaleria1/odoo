from calendar import monthrange
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from itertools import islice

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.tools.date_utils import get_timedelta, occurrences_after

from odoo.addons.base.models.mixin_recurrence_rule import REPEAT_TYPE_COUNT
from odoo.addons.base.models.resource_utils import peak_capacity

_debug = DebugLog(__name__)


class PlanningRecurrency(models.Model):
    _name = "planning.recurrency"
    _description = "Planning Recurrence"
    _inherit = ["mixin.recurrence.rule"]

    slot_ids = fields.One2many(
        comodel_name="planning.slot",
        inverse_name="recurrency_id",
        string="Related Planning Entries",
    )
    repeat_interval = fields.Integer(required=True)
    repeat_unit = fields.Selection(required=True)
    repeat_type = fields.Selection(
        selection_add=[REPEAT_TYPE_COUNT],
        string="Weeks",
        ondelete={REPEAT_TYPE_COUNT[0]: "set default"},
    )
    repeat_until = fields.Datetime(
        help="Up to which date should the plannings be repeated"
    )
    repeat_number = fields.Integer(
        string="Repetitions",
        help="No Of Repetitions of the plannings",
    )
    last_generated_end_datetime = fields.Datetime(
        export_string_translation=False,
        readonly=True,
    )
    date_recurrence_origin = fields.Datetime(
        export_string_translation=False,
        copy=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=True,
        required=True,
    )

    _check_until_limit = models.Constraint(
        "CHECK((repeat_type = 'until' AND repeat_until IS NOT NULL) OR (repeat_type != 'until'))",
        "A recurrence repeating itself until a certain date must have its limit set",
    )

    @api.constrains("repeat_number", "repeat_type")
    def _check_repeat_number(self) -> None:
        if self.filtered(lambda t: t.repeat_type == "count" and t.repeat_number < 0):
            raise ValidationError(
                self.env._("The number of repetitions cannot be negative.")
            )

    @api.constrains("company_id", "slot_ids")
    def _check_multi_company(self) -> None:
        for recurrency in self:
            if any(
                recurrency.company_id != planning.company_id
                for planning in recurrency.slot_ids
            ):
                raise ValidationError(
                    self.env._("A shift must be in the same company as its recurrence.")
                )

    def write(self, vals):
        if "date_recurrence_origin" not in vals:
            recadenced = self.filtered(
                lambda recurrency: any(
                    fname in vals and vals[fname] != recurrency[fname]
                    for fname in ("repeat_interval", "repeat_unit")
                )
            )
            if recadenced:
                super(PlanningRecurrency, recadenced).write(
                    {"date_recurrence_origin": False}
                )
        return super().write(vals)

    @api.depends("repeat_type", "repeat_interval", "repeat_until")
    def _compute_display_name(self):
        for recurrency in self:
            if recurrency.repeat_type == "forever":
                name = self.env._(
                    "Forever, every %s week(s)", recurrency.repeat_interval
                )
            else:
                name = self.env._(
                    "Every %(repeat_interval)s week(s) until %(repeat_until)s",
                    repeat_interval=recurrency.repeat_interval,
                    repeat_until=recurrency.repeat_until,
                )
            recurrency.display_name = name

    @api.model
    def _cron_schedule_next(self) -> None:
        companies = self.env["res.company"].search([])
        now = fields.Datetime.now()
        for company in companies:
            delta = get_timedelta(company.planning_generation_interval, "month")

            recurrencies = self.search(
                [
                    "&",
                    "&",
                    ("company_id", "=", company.id),
                    ("last_generated_end_datetime", "<", now + delta),
                    "|",
                    ("repeat_until", "=", False),
                    ("repeat_until", ">", now - delta),
                ]
            )
            _debug.pipeline(
                "recurrency_cron",
                company=company,
                recurrencies=recurrencies,
                until=str(now + delta),
            )
            recurrencies._repeat_slot(now + delta)

    def _repeat_slot(self, stop_datetime=False) -> None:
        for recurrency in self:
            recurrency._generate_next_slots(stop_datetime)

    def _generate_next_slots(self, stop_datetime) -> None:
        self.check_singleton()
        PlanningSlot = self.env["planning.slot"]
        slot = PlanningSlot.search(
            [("recurrency_id", "=", self.id)],
            limit=1,
            order="start_datetime DESC",
        )

        if slot:
            if not self.date_recurrence_origin:
                self.date_recurrence_origin = self._resolve_recurrence_origin(slot)
            # find the end of the recurrence
            recurrence_end_dt = False
            if self.repeat_type == "until":
                recurrence_end_dt = self.repeat_until

            # find end of generation period (either the end of recurrence (if this one ends before the cron period), or the given `stop_datetime` (usually the cron period))
            recurrency_stop_datetime = (
                stop_datetime
                or PlanningSlot._add_delta_with_dst(
                    fields.Datetime.now(),
                    get_timedelta(
                        self.company_id.planning_generation_interval, "month"
                    ),
                )
            )
            misc_recurrence_stop = self._get_misc_recurrence_stop()
            range_limit = min(
                dt
                for dt in [
                    recurrence_end_dt,
                    recurrency_stop_datetime,
                    misc_recurrence_stop,
                ]
                if dt
            )
            slot_duration = slot.end_datetime - slot.start_datetime

            # add timezone information to the start and end of the recurrence duration (needed for company / resource availability computation)
            start_duration = slot.start_datetime.replace(tzinfo=UTC)
            end_duration = range_limit.replace(tzinfo=UTC)

            # get the company's work intervals as well as the public holidays
            company_calendar_working_days = (
                self.company_id.resource_calendar_id._work_intervals_batch(
                    start_duration, end_duration
                )[False]
            )

            # get the resource of the recurring shift
            resource = (
                slot.resource_id
                or self.slot_ids.filtered("resource_id")
                .sorted("start_datetime")[-1:]
                .resource_id
            )

            # We check whether the slot was generated outisde working days (includes public holidays), if so we will generate the recurrent slots normally
            days_of_slot = {
                slot.start_datetime.date() + timedelta(days=i)
                for i in range(slot_duration.days + 1)
            }
            is_slot_outside_working_days = not days_of_slot <= {
                start.date() for start, stop, dummy in company_calendar_working_days
            }

            def can_slot_be_generated(
                next_start,
                company_calendar_working_days=company_calendar_working_days,
                resource=resource,
                is_slot_outside_working_days=is_slot_outside_working_days,
            ) -> bool:
                next_start_utc = next_start.replace(tzinfo=UTC)
                lands_on_working_day = any(
                    next_start_utc.date() == start.date()
                    for start, stop, dummy in company_calendar_working_days
                )
                return bool(
                    lands_on_working_day
                    or (resource and resource._is_flexible())
                    or is_slot_outside_working_days
                )

            def get_all_next_starts(
                recurrency=self,
                slot=slot,
                range_limit=range_limit,
                can_slot_be_generated=can_slot_be_generated,
            ):
                generated_recurrency_slots = -1
                if self.repeat_type == "count":
                    generated_recurrency_slots = self.env["planning.slot"].search_count(
                        [("recurrency_id", "=", self.id)]
                    )
                occurrences = occurrences_after(
                    self.date_recurrence_origin,
                    self._get_generation_after(slot),
                    self.repeat_interval,
                    self.repeat_unit,
                    PlanningSlot._get_tzinfo(),
                )
                for next_start in islice(occurrences, 365 * 5):
                    if (
                        next_start >= range_limit
                        or generated_recurrency_slots >= self.repeat_number
                    ):
                        return
                    if not can_slot_be_generated(next_start):
                        continue
                    generated_recurrency_slots += self.repeat_type == "count"
                    yield next_start

            # Load all consumers through Resource, including the full local
            # weeks needed to account for flexible effort outside these slots.
            booking_start, booking_stop = resource._get_flexible_week_bounds(
                start_duration, (range_limit + slot_duration).replace(tzinfo=UTC)
            )
            loads = self.env["resource.reservation"]._get_booking_load_batch(
                resource,
                booking_start.replace(tzinfo=None),
                booking_stop.replace(tzinfo=None),
            )
            bookings = loads.get(resource.id, [])
            resource_availability = resource._get_valid_work_intervals(
                start_duration, end_duration
            )[0][resource.id]
            is_slot_outside_working_hours = all(
                slot.start_datetime.replace(tzinfo=UTC) >= stop
                or slot.end_datetime.replace(tzinfo=UTC) <= start
                for start, stop, _dummy in resource_availability
            )
            flexible = resource and resource._is_flexible()
            budgeted = flexible and not resource._is_fully_flexible()
            work_intervals, day_limits, week_limits = {}, {}, {}
            remaining_days, remaining_weeks = {}, {}
            if flexible:
                work_intervals, day_limits, week_limits = (
                    resource._get_flexible_resource_valid_work_intervals(
                        booking_start, booking_stop
                    )
                )
            if budgeted:
                remaining_days = deepcopy(day_limits[resource.id])
                remaining_weeks = deepcopy(week_limits[resource.id])
                booked_hours = resource._get_flexible_booking_hours_per_day(
                    loads, booking_start, booking_stop
                )
                for day, hours in booked_hours[resource.id].items():
                    remaining_days[day] -= hours
                    remaining_weeks[resource._get_week_of(day)] -= hours

            def can_slot_be_assigned(
                next_start,
                next_end,
                percentage,
                resource=resource,
                bookings=bookings,
                resource_availability=resource_availability,
                is_slot_outside_working_hours=is_slot_outside_working_hours,
                flexible=flexible,
                budgeted=budgeted,
                work_intervals=work_intervals,
                day_limits=day_limits,
                week_limits=week_limits,
                remaining_days=remaining_days,
                remaining_weeks=remaining_weeks,
            ) -> bool:
                if not resource or not resource.active:
                    return False
                if (
                    peak_capacity(bookings, next_start, next_end) + percentage
                    > resource.booking_limit_percentage + 1e-7
                ):
                    return False
                start_utc = next_start.replace(tzinfo=UTC)
                end_utc = next_end.replace(tzinfo=UTC)
                if not (
                    flexible
                    or is_slot_outside_working_hours
                    or any(
                        start_utc < stop and end_utc > start
                        for start, stop, _dummy in resource_availability
                    )
                ):
                    return False
                if flexible:
                    candidate = (
                        Intervals([(start_utc, end_utc, PlanningSlot)])
                        & work_intervals[resource.id]
                    )
                    if percentage > 0 and not candidate:
                        return False
                if budgeted:
                    hours_per_day = defaultdict(float)
                    available_hours = resource._get_flexible_resource_work_hours(
                        candidate,
                        day_limits[resource.id],
                        week_limits[resource.id],
                        hours_per_day,
                    )
                    if percentage > 0 and available_hours <= 0:
                        return False
                    needed_per_week = defaultdict(float)
                    for day, hours in hours_per_day.items():
                        effort = hours * percentage / 100
                        week = resource._get_week_of(day)
                        needed_per_week[week] += effort
                        if (
                            effort > remaining_days.get(day, 0.0) + 1e-7
                            or needed_per_week[week]
                            > remaining_weeks.get(week, 0.0) + 1e-7
                        ):
                            return False
                    for day, hours in hours_per_day.items():
                        remaining_days[day] -= hours * percentage / 100
                    for week, hours in needed_per_week.items():
                        remaining_weeks[week] -= hours
                bookings.append((next_start, next_end, percentage))
                return True

            slot_values_list = []
            for next_start in get_all_next_starts():
                next_end = next_start + slot_duration
                # Check that the duration is not longer than the month of the start to avoid overlapping slots
                if slot.repeat_unit == "month":
                    days_in_month = monthrange(next_start.year, next_start.month)[1]
                    if slot_duration.days >= days_in_month:
                        next_end -= timedelta(
                            days=slot_duration.days - (days_in_month - 1)
                        )
                slot_values = slot.copy_data(
                    {
                        "start_datetime": next_start,
                        "end_datetime": next_end,
                        "recurrency_id": self.id,
                        "company_id": self.company_id.id,
                        "repeat": True,
                        "state": "1_draft",
                    }
                )[0]
                slot_values["resource_id"] = (
                    resource.id
                    if can_slot_be_assigned(
                        next_start, next_end, slot.allocated_percentage
                    )
                    else False
                )
                slot_values_list.append(slot_values)
            if slot_values_list:
                _debug.lifecycle(
                    "recurrency_slots_generated",
                    recurrency=self,
                    slots=len(slot_values_list),
                )
                PlanningSlot.create(slot_values_list)
                self.write(
                    {
                        "last_generated_end_datetime": slot_values_list[-1][
                            "start_datetime"
                        ]
                    }
                )

        else:
            _debug.lifecycle("recurrency_exhausted", recurrency=self)
            self.unlink()

    def _get_next_occurrence(self, origin, after):
        return next(
            occurrences_after(
                origin,
                after,
                self.repeat_interval,
                self.repeat_unit,
                self.env["planning.slot"]._get_tzinfo(),
            )
        )

    def _is_occurrence(self, origin, moment) -> bool:
        return (
            self._get_next_occurrence(origin, moment - timedelta(seconds=1)) == moment
        )

    def _resolve_recurrence_origin(self, latest_slot):
        self.check_singleton()
        earliest = self.env["planning.slot"].search(
            [("recurrency_id", "=", self.id)], limit=1, order="start_datetime ASC"
        )
        if earliest.start_datetime < latest_slot.start_datetime and self._is_occurrence(
            earliest.start_datetime, latest_slot.start_datetime
        ):
            return earliest.start_datetime
        return latest_slot.start_datetime

    def _get_generation_after(self, latest_slot):
        self.check_singleton()
        after = latest_slot.start_datetime
        origin = self.date_recurrence_origin
        if self._is_occurrence(origin, after):
            return after
        # A latest shift moved off its date on its own still stands for the
        # occurrence it was generated at, which must not be generated again.
        replaced = self._get_next_occurrence(origin, after)
        if (
            self.last_generated_end_datetime
            and replaced <= self.last_generated_end_datetime
        ):
            return replaced
        return after

    def _remove_slot(self, start_datetime) -> None:
        slots = self.env["planning.slot"].search(
            [
                ("recurrency_id", "in", self.ids),
                ("start_datetime", ">=", start_datetime),
                ("state", "=", "1_draft"),
            ]
        )
        slots.unlink()

    def _get_misc_recurrence_stop(self):
        """
        If there are additional limitations on until when the recurring shifts can be generated, this method will return the
        earliest date after which shifts cannot be generated under this additional limitation.

        By default, we generate recurring shifts until the repeat_until date specified by the user or for 6 months in the future.
        If there are any additional limitations that prevent us from generating the slot until either of those two datetimes, they
        should be returned here.

        Example: this method is extended in the planning_contract module - to plan until the end of the contract period. That way,
        if we plan a shift on 1/1/25 to repeat weekly until 1/4/25 but the resource's contract ends in 1/3/25, we will only repeat the
        slot until 1/3/25 and not until 1/4/25. This method should thus return the detatime 1/3/25 23:59:59.
        """
        res = datetime.max.replace(tzinfo=UTC)
        sorted_slots = self.slot_ids.sorted("end_datetime")
        initial_slot, last_slot = sorted_slots[0], sorted_slots[-1]
        end_contract = last_slot.employee_id.sudo().version_id.contract_date_end
        end_contract = (
            datetime.combine(end_contract, time.max, tzinfo=UTC)
            if end_contract
            else res
        )
        # If the initial slot that we are repeating is planned after the end of the resource contract, we generate the slots
        # on out-of-contract dates normally.
        # Convert the result back to the ORM's naive UTC representation.
        if initial_slot.start_datetime.replace(tzinfo=UTC) > end_contract:
            return res.replace(tzinfo=None)
        return min(end_contract, res).replace(tzinfo=None)
