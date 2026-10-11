from calendar import monthrange
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools.date_utils import (
    Anchor,
    anchor_day,
    get_timedelta,
    next_anchor,
    previous_anchor,
)

from odoo.addons.base.models.mixin_recurrence_rule import (
    REPEAT_UNIT_SELECTION,
    WEEKDAY_SELECTION,
)

_debug = DebugLog(__name__)

WEEKDAY_INDEX = {code: index for index, (code, _label) in enumerate(WEEKDAY_SELECTION)}

DAY_SELECTION = [(str(day), str(day)) for day in range(1, 32)]
LAST_DAY = "last"
ANCHOR_DAY_SELECTION = [*DAY_SELECTION, (LAST_DAY, "Last day")]

MONTH_SELECTION = [
    ("1", "January"),
    ("2", "February"),
    ("3", "March"),
    ("4", "April"),
    ("5", "May"),
    ("6", "June"),
    ("7", "July"),
    ("8", "August"),
    ("9", "September"),
    ("10", "October"),
    ("11", "November"),
    ("12", "December"),
]

FREQUENCY_CADENCE = {
    "hourly": ("day", False, "hour"),
    "daily": ("day", False, "period"),
    "weekly": ("week", False, "period"),
    "bimonthly": ("month", True, "period"),
    "monthly": ("month", False, "period"),
    "biyearly": ("year", True, "period"),
    "yearly": ("year", False, "period"),
}


class HrLeaveAccrualLevel(models.Model):
    _name = "hr.leave.accrual.level"
    _description = "Accrual Plan Level"
    _order = "sequence asc"

    sequence = fields.Integer(
        string="sequence",
        compute="_compute_sequence",
        store=True,
        help="Sequence is generated automatically by start time delta.",
    )
    accrual_plan_id = fields.Many2one(
        comodel_name="hr.leave.accrual.plan",
        default=lambda self: self.env.context.get("active_id", None),
        index=True,
        required=True,
        ondelete="cascade",
    )
    is_based_on_worked_time = fields.Boolean(
        related="accrual_plan_id.is_based_on_worked_time",
        export_string_translation=False,
    )
    accrued_gain_time = fields.Selection(
        related="accrual_plan_id.accrued_gain_time",
        export_string_translation=False,
    )
    start_count = fields.Integer(
        export_string_translation=False,
        help="The accrual starts after a defined period from the allocation start date. This field defines the number of days, months or years after which accrual is used.",
    )
    start_type = fields.Selection(
        selection=[("day", "Days"), ("month", "Months"), ("year", "Years")],
        export_string_translation=False,
        default="day",
        required=True,
        help="This field defines the unit of time after which the accrual starts.",
    )
    milestone_date = fields.Selection(
        selection=[("creation", "At allocation creation"), ("after", "After")],
        export_string_translation=False,
        compute="_compute_milestone_date",
        inverse="_inverse_milestone_date",
        default="creation",
        store=True,
        readonly=False,
        required=True,
    )
    added_value = fields.Float(
        export_string_translation=False,
        digits=(16, 5),
        default=1,
        required=True,
    )
    added_value_type = fields.Selection(
        selection=[("day", "Day(s)"), ("hour", "Hour(s)")],
        export_string_translation=False,
        compute="_compute_added_value_type",
        inverse="_inverse_added_value_type",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    accrual_basis = fields.Selection(
        selection=[("period", "Per Period"), ("hour", "Per Hour")],
        export_string_translation=False,
        default="period",
        required=True,
        help="Whether the added value is granted once per period or for each hour"
        " planned in it.",
    )
    repeat_unit = fields.Selection(
        selection=REPEAT_UNIT_SELECTION,
        string="Every",
        export_string_translation=False,
        default="month",
        required=True,
    )
    repeat_twice = fields.Boolean(
        string="Twice per Period",
        help="Two anchors in each month or year instead of one",
    )
    repeat_weekday = fields.Selection(
        selection=WEEKDAY_SELECTION,
        string="Weekday",
        default="MON",
    )
    repeat_day = fields.Selection(
        selection=ANCHOR_DAY_SELECTION,
        compute="_compute_repeat_day",
        default="1",
        store=True,
        readonly=False,
    )
    repeat_month = fields.Selection(
        selection=MONTH_SELECTION,
        default="1",
    )
    repeat_second_day = fields.Selection(
        selection=ANCHOR_DAY_SELECTION,
        compute="_compute_repeat_second_day",
        store=True,
        readonly=False,
    )
    repeat_second_month = fields.Selection(
        selection=MONTH_SELECTION,
        default="7",
    )

    frequency = fields.Selection(
        selection=[
            ("hourly", "Hourly"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("bimonthly", "Twice a month"),
            ("monthly", "Monthly"),
            ("biyearly", "Twice a year"),
            ("yearly", "Yearly"),
        ],
        compute="_compute_frequency",
        inverse="_inverse_frequency",
    )
    cap_accrued_time = fields.Boolean(
        export_string_translation=False,
        help="When the field is checked the balance of an allocation using this accrual plan will never exceed the specified amount.",
    )
    maximum_leave = fields.Float(
        export_string_translation=False,
        digits=(16, 2),
        compute="_compute_maximum_leave",
        default=0,
        store=True,
        readonly=False,
        help="Choose a cap for this accrual.",
    )
    cap_accrued_time_yearly = fields.Boolean(
        export_string_translation=False,
        store=True,
        readonly=False,
        help="When the field is checked the total amount accrued each year will be capped at the specified amount",
    )
    maximum_leave_yearly = fields.Float(
        export_string_translation=False,
        digits=(16, 2),
    )
    yearly_gain = fields.Float(
        export_string_translation=False,
        compute="_compute_yearly_gain",
    )
    can_be_carryover = fields.Boolean(
        related="accrual_plan_id.can_be_carryover",
        export_string_translation=False,
        readonly=True,
    )
    action_with_unused_accruals = fields.Selection(
        selection=[("lost", "Lost"), ("all", "Carried over")],
        export_string_translation=False,
        compute="_compute_action_with_unused_accruals",
        default="lost",
        store=True,
        readonly=False,
        required=True,
        help="When the Carry-Over Time is reached, according to Plan's setting, select what you want "
        "to happen with the unused time off: Lost (time will be reset to zero), Carried over (accrued time carried over to "
        "the next period.)",
    )
    carryover_options = fields.Selection(
        selection=[("unlimited", "Unlimited"), ("limited", "Up to")],
        export_string_translation=False,
        compute="_compute_carryover_options",
        default="unlimited",
        store=True,
        readonly=False,
        required=True,
        help="You can limit the accrued time carried over for the next period.",
    )
    postpone_max_days = fields.Integer(
        export_string_translation=False,
        help="Set a maximum of accruals an allocation keeps at the end of the year.",
    )
    can_modify_value_type = fields.Boolean(
        export_string_translation=False,
        compute="_compute_can_modify_value_type",
        default=False,
    )
    accrual_validity = fields.Boolean(
        export_string_translation=False,
        compute="_compute_accrual_validity",
        store=True,
        readonly=False,
    )
    accrual_validity_count = fields.Integer(
        export_string_translation=False,
        default="1",
        help="You can define a period of time where the days carried over will be available",
    )
    accrual_validity_type = fields.Selection(
        selection=[("day", "Days"), ("month", "Months")],
        export_string_translation=False,
        default="day",
        required=True,
        help="This field defines the unit of time after which the accrual ends.",
    )

    _start_count_check = models.Constraint(
        "CHECK((start_count > 0 AND milestone_date = 'after') OR (start_count = 0 AND milestone_date = 'creation'))",
        "You can not start an accrual in the past.",
    )
    _added_value_greater_than_zero = models.Constraint(
        "CHECK(added_value > 0)",
        "You must give a rate greater than 0 in accrual plan levels.",
    )
    _valid_postpone_max_days_value = models.Constraint(
        "CHECK(action_with_unused_accruals <> 'all' OR carryover_options <> 'limited' OR COALESCE(postpone_max_days, 0) > 0)",
        "You cannot have a maximum quantity to carryover set to 0.",
    )
    _valid_accrual_validity_value = models.Constraint(
        "CHECK(accrual_validity IS NOT TRUE OR COALESCE(accrual_validity_count, 0) > 0)",
        "You cannot have an accrual validity time set to 0.",
    )
    _valid_yearly_cap_value = models.Constraint(
        "CHECK(cap_accrued_time_yearly IS NOT TRUE OR COALESCE(maximum_leave_yearly, 0) > 0)",
        "You cannot have a cap on yearly accrued time without setting a maximum amount.",
    )

    @api.constrains("cap_accrued_time", "maximum_leave")
    def _check_maximum_leaves(self) -> None:
        for level in self:
            if level.cap_accrued_time and level.maximum_leave <= 0:
                raise ValidationError(
                    self.env._(
                        "You cannot have a balance cap on accrued time set to 0."
                    )
                )

    @api.depends("start_count", "start_type")
    def _compute_sequence(self) -> None:
        start_type_multipliers = {
            "day": 1,
            "month": 30,
            "year": 365,
        }
        for level in self:
            level.sequence = (
                level.start_count * start_type_multipliers[level.start_type]
            )

    @api.depends(
        "accrual_plan_id",
        "accrual_plan_id.level_ids",
        "accrual_plan_id.time_off_type_id",
    )
    def _compute_can_modify_value_type(self) -> None:
        for level in self:
            level.can_modify_value_type = (
                not level.accrual_plan_id.time_off_type_id
                and level.accrual_plan_id.level_ids
                and level.accrual_plan_id.level_ids[0] == level
            )

    def _inverse_added_value_type(self) -> None:
        for level in self:
            if (
                level.accrual_plan_id.level_ids
                and level.accrual_plan_id.level_ids[0] == level
            ):
                level.accrual_plan_id.added_value_type = level.added_value_type

    @api.depends(
        "accrual_plan_id",
        "accrual_plan_id.level_ids",
        "accrual_plan_id.added_value_type",
        "accrual_plan_id.time_off_type_id",
    )
    def _compute_added_value_type(self) -> None:
        for level in self:
            if level.accrual_plan_id.time_off_type_id:
                level.added_value_type = (
                    "day"
                    if level.accrual_plan_id.time_off_type_id.request_unit
                    in ["day", "half_day"]
                    else "hour"
                )
            elif (
                level.accrual_plan_id.level_ids
                and level.accrual_plan_id.level_ids[0] != level
            ):
                level.added_value_type = level.accrual_plan_id.level_ids[
                    0
                ].added_value_type
            elif not level.added_value_type:
                level.added_value_type = "day"

    @staticmethod
    def _clamp_day(day, month):
        if day == LAST_DAY:
            return day
        return str(min(monthrange(2020, int(month))[1], int(day)))

    @api.depends("repeat_month", "repeat_unit")
    def _compute_repeat_day(self) -> None:
        for record in self:
            if (
                record.repeat_unit == "year"
                and record.repeat_day
                and record.repeat_month
            ):
                clamped = self._clamp_day(record.repeat_day, record.repeat_month)
                if _debug.logic.enabled and clamped != record.repeat_day:
                    _debug.logic(
                        "recurrence.anchor_day_clamped",
                        record=record.id,
                        field="repeat_day",
                        month=record.repeat_month,
                        day=record.repeat_day,
                        clamped=clamped,
                    )
                record.repeat_day = clamped

    @api.depends("repeat_second_month", "repeat_unit", "repeat_twice")
    def _compute_repeat_second_day(self) -> None:
        for record in self:
            if not record.repeat_twice:
                continue
            if not record.repeat_second_day:
                record.repeat_second_day = (
                    "15" if record.repeat_unit == "month" else "1"
                )
                _debug.logic(
                    "recurrence.second_anchor_defaulted",
                    record=record.id,
                    unit=record.repeat_unit,
                    day=record.repeat_second_day,
                )
            elif record.repeat_unit == "year" and record.repeat_second_month:
                clamped = self._clamp_day(
                    record.repeat_second_day, record.repeat_second_month
                )
                if _debug.logic.enabled and clamped != record.repeat_second_day:
                    _debug.logic(
                        "recurrence.anchor_day_clamped",
                        record=record.id,
                        field="repeat_second_day",
                        month=record.repeat_second_month,
                        day=record.repeat_second_day,
                        clamped=clamped,
                    )
                record.repeat_second_day = clamped

    @api.constrains(
        "repeat_unit",
        "repeat_twice",
        "repeat_weekday",
        "repeat_day",
        "repeat_month",
        "repeat_second_day",
        "repeat_second_month",
    )
    def _check_repeat_anchors(self) -> None:
        for record in self:
            if record.repeat_unit == "week" and not record.repeat_weekday:
                _debug.logic(
                    "recurrence.anchors_rejected",
                    record=record.id,
                    reason="weekday_missing",
                )
                raise ValidationError(self.env._("A weekly schedule needs a weekday."))
            if record.repeat_unit not in ("month", "year"):
                continue
            if not record.repeat_day or (
                record.repeat_twice and not record.repeat_second_day
            ):
                _debug.logic(
                    "recurrence.anchors_rejected",
                    record=record.id,
                    reason="day_missing",
                )
                raise ValidationError(
                    self.env._("A monthly or yearly schedule needs a day.")
                )
            if record.repeat_unit == "year" and (
                not record.repeat_month
                or (record.repeat_twice and not record.repeat_second_month)
            ):
                _debug.logic(
                    "recurrence.anchors_rejected",
                    record=record.id,
                    reason="month_missing",
                )
                raise ValidationError(self.env._("A yearly schedule needs a month."))
            if not record.repeat_twice:
                continue
            anchors = record._get_recurrence_anchors()
            first, second = map(record._get_boundary_in_reference_period, anchors)
            one_period = relativedelta(**{f"{record.repeat_unit}s": 1})
            _debug.logic(
                "recurrence.anchors_checked",
                record=record.id,
                unit=record.repeat_unit,
                anchors=len(anchors),
                last_day=any(anchor.last_day for anchor in anchors),
                ordered=first < second,
            )
            if any(anchor.last_day for anchor in anchors) and second in (
                first,
                first + one_period,
            ):
                _debug.logic(
                    "recurrence.anchors_rejected",
                    record=record.id,
                    reason="same_period_closed",
                )
                raise ValidationError(
                    self.env._(
                        "The last day of a month and the first day of the next one "
                        "close the same period, so they cannot be the two dates."
                    )
                )
            if first >= second:
                _debug.logic(
                    "recurrence.anchors_rejected",
                    record=record.id,
                    reason="unordered",
                    unit=record.repeat_unit,
                )
                raise ValidationError(
                    self.env._("The first day must be lower than the second day.")
                    if record.repeat_unit == "month"
                    else self.env._(
                        "The first date must be earlier in the year than the second date."
                    )
                )
            first_day, second_day = map(record._get_anchor_day_in_short_period, anchors)
            if first_day == second_day:
                _debug.logic(
                    "recurrence.anchors_rejected",
                    record=record.id,
                    reason="merged_in_short_period",
                    unit=record.repeat_unit,
                )
                raise ValidationError(
                    self.env._("The two dates fall on the same day in shorter months.")
                )

    @staticmethod
    def _get_boundary_in_reference_period(anchor):
        first = date(2024, anchor.month or 1, 1)
        if anchor.last_day:
            return first + relativedelta(months=1)
        return first.replace(day=min(anchor.day, monthrange(2024, first.month)[1]))

    @staticmethod
    def _get_anchor_day_in_short_period(anchor):
        month = anchor.month or 2
        length = monthrange(2023, month)[1]
        return date(2023, month, length if anchor.last_day else min(anchor.day, length))

    @staticmethod
    def _prepare_day_anchor(day, month):
        if day == LAST_DAY:
            return Anchor(month=month, last_day=True)
        return Anchor(day=int(day), month=month)

    def _get_recurrence_anchors(self):
        self.check_singleton()
        unit = self.repeat_unit
        if unit == "day":
            return []
        if unit == "week":
            return [Anchor(weekday=WEEKDAY_INDEX[self.repeat_weekday])]
        month = int(self.repeat_month) if unit == "year" else None
        anchors = [self._prepare_day_anchor(self.repeat_day, month)]
        if self.repeat_twice:
            second_month = int(self.repeat_second_month) if unit == "year" else None
            anchors.append(
                self._prepare_day_anchor(self.repeat_second_day, second_month)
            )
        _debug.logic(
            "recurrence.anchors_built",
            record=self.id,
            unit=unit,
            anchors=len(anchors),
            twice=bool(self.repeat_twice),
        )
        return anchors

    def _get_next_anchor(self, after):
        return next_anchor(after, self.repeat_unit, self._get_recurrence_anchors())

    def _get_previous_anchor(self, on):
        return previous_anchor(on, self.repeat_unit, self._get_recurrence_anchors())

    def _get_anchor_day(self, boundary):
        if self.repeat_unit in ("day", "week"):
            return boundary
        return anchor_day(boundary, self.repeat_unit, self._get_recurrence_anchors())

    def _get_frequency_cadences(self):
        return FREQUENCY_CADENCE

    @api.depends("repeat_unit", "repeat_twice", "accrual_basis")
    def _compute_frequency(self) -> None:
        by_cadence = {
            cadence: code for code, cadence in self._get_frequency_cadences().items()
        }
        for level in self:
            level.frequency = by_cadence.get(
                (level.repeat_unit, level.repeat_twice, level.accrual_basis)
            )

    def _inverse_frequency(self) -> None:
        cadences = self._get_frequency_cadences()
        for level in self:
            if level.frequency in cadences:
                (
                    level.repeat_unit,
                    level.repeat_twice,
                    level.accrual_basis,
                ) = cadences[level.frequency]

    @api.depends("cap_accrued_time")
    def _compute_maximum_leave(self) -> None:
        for level in self:
            if not level.cap_accrued_time:
                level.maximum_leave = 0

    @api.depends("frequency", "added_value", "is_based_on_worked_time")
    def _compute_yearly_gain(self) -> None:
        company_calendar = self.env.company.resource_calendar_id
        hours_per_week = company_calendar.hours_per_week
        days_per_week = company_calendar._get_days_per_week()
        for level in self:
            if level.frequency == "hourly":
                gain = level.added_value * 52 * hours_per_week
            elif level.frequency == "daily":
                if level.is_based_on_worked_time:
                    gain = level.added_value * 52 * days_per_week
                else:
                    gain = level.added_value * 365
            elif level.frequency == "weekly":
                gain = level.added_value * 52
            elif level.frequency == "bimonthly":
                gain = level.added_value * 24
            elif level.frequency == "monthly":
                gain = level.added_value * 12
            elif level.frequency == "biyearly":
                gain = level.added_value * 2
            elif level.frequency == "yearly":
                gain = level.added_value
            else:
                gain = 0
            level.yearly_gain = gain

    @api.depends("can_be_carryover")
    def _compute_action_with_unused_accruals(self) -> None:
        for level in self:
            if not level.can_be_carryover:
                level.action_with_unused_accruals = "lost"

    @api.depends("action_with_unused_accruals")
    def _compute_carryover_options(self) -> None:
        for level in self:
            if level.action_with_unused_accruals == "lost":
                level.carryover_options = "unlimited"

    @api.depends("action_with_unused_accruals")
    def _compute_accrual_validity(self) -> None:
        for level in self:
            if level.action_with_unused_accruals == "lost":
                level.accrual_validity = False

    @api.depends("start_count", "milestone_date")
    def _compute_milestone_date(self) -> None:
        for level in self:
            if level.start_count == 0:
                level.milestone_date = "creation"

    def _inverse_milestone_date(self) -> None:
        for level in self:
            if level.milestone_date == "creation":
                level.start_count = 0

    def _get_hourly_bases(self):
        return ["hour"]

    def _get_level_transition_date(self, allocation_start):
        return allocation_start + get_timedelta(self.start_count, self.start_type)

    def action_save_new(self):
        return self.accrual_plan_id.action_create_accrual_plan_level()
