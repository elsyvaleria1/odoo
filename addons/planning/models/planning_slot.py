from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from math import modf
from random import shuffle
from typing import TYPE_CHECKING, Literal, Self
from urllib.parse import urlencode as url_encode
from zoneinfo import ZoneInfoNotFoundError

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, UserError
from odoo.fields import Datetime, Domain
from odoo.libs.datetime import timezone, wall_to_utc
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.libs.numbers import float_is_zero, float_repr, float_round, float_split_str
from odoo.tools import (
    DEFAULT_SERVER_DATETIME_FORMAT,
    format_date,
    format_datetime,
    format_time,
    frozendict,
)
from odoo.tools.date_utils import (
    get_intervals_hours,
    get_timedelta,
)

from odoo.addons.base.models.mixin_recurrence_rule import (
    REPEAT_TYPE_COUNT,
    REPEAT_TYPE_SELECTION,
    REPEAT_UNIT_SELECTION,
)
from odoo.addons.base.models.resource_utils import (
    FirstServedClaim,
    last_day_of,
    peak_capacity,
)

if TYPE_CHECKING:
    from vobject.base import Component

_debug = DebugLog(__name__)


def days_span(start_datetime, end_datetime):
    if not isinstance(start_datetime, datetime):
        raise TypeError
    if not isinstance(end_datetime, datetime):
        raise TypeError
    return (last_day_of(start_datetime, end_datetime) - start_datetime.date()).days + 1


class PlanningSlot(models.Model):
    _name = "planning.slot"
    _description = "Planning Shift"
    _inherit = ["mixin.resource.scheduling"]
    _reservation_sync_manual = True
    _order = "start_datetime desc, id desc"
    _rec_name = "name"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    def _get_default_start_datetime(self):
        return datetime.combine(fields.Date.context_today(self), time.min)

    def _get_default_end_datetime(self):
        return datetime.combine(fields.Date.context_today(self), time.max)

    name = fields.Text(string="Note")
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        group_expand="_group_expand_resource_id",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    resource_type = fields.Selection(related="resource_id.type")
    resource_color = fields.Integer(
        related="resource_id.color",
        string="Resource color",
    )
    resource_roles = fields.Many2many(related="resource_id.role_ids")
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        compute="_compute_employee_id",
        store=True,
    )
    work_email = fields.Char(
        related="resource_id.partner_id.email",
        string="Work Email",
    )
    work_location_id = fields.Many2one(related="employee_id.work_location_id")
    department_id = fields.Many2one(
        related="employee_id.department_id",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        related="resource_id.user_id",
        string="User",
        readonly=True,
    )
    manager_id = fields.Many2one(
        related="employee_id.parent_id",
    )
    job_title = fields.Char(related="employee_id.job_title")
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_planning_slot_company_id",
        store=True,
        readonly=False,
        required=True,
    )
    role_id = fields.Many2one(
        comodel_name="resource.role",
        compute="_compute_role_id",
        store=True,
        copy=True,
        readonly=False,
        group_expand="_read_group_role_id",
        help="Define the roles your resources will perform (e.g. Chef, Bartender, Waiter). Create open shifts based on the roles needed for a mission, then assign those shifts to available resources.",
    )
    color = fields.Integer(compute="_compute_color")
    was_copied = fields.Boolean(
        string="This Shift Was Copied From Previous Week",
        default=False,
        readonly=True,
    )

    start_datetime = fields.Datetime(
        string="Start Date",
        compute="_compute_datetime",
        store=True,
        copy=True,
        readonly=False,
        required=True,
    )
    end_datetime = fields.Datetime(
        string="End Date",
        compute="_compute_datetime",
        store=True,
        copy=True,
        readonly=False,
        required=True,
    )
    allow_self_unassign = fields.Boolean(
        string="Let Employee Unassign Themselves",
        compute="_compute_allow_self_unassign",
    )
    self_unassign_days_before = fields.Integer(
        related="company_id.planning_self_unassign_days_before",
        string="Days before shift for unassignment",
    )
    unassign_deadline = fields.Datetime(
        string="Deadline for unassignment",
        export_string_translation=False,
        compute="_compute_unassign_deadline",
    )
    is_unassign_deadline_passed = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_unassign_deadline_passed",
    )
    conflicting_slot_ids = fields.Many2many(
        comodel_name="planning.slot",
        export_string_translation=False,
        compute="_compute_conflicting_slot_ids",
    )
    overlap_slot_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_overlap_slot_count",
        search="_search_overlap_slot_count",
    )
    is_past = fields.Boolean(
        string="Is This Shift In The Past?",
        export_string_translation=False,
        compute="_compute_past_shift",
    )
    is_users_role = fields.Boolean(
        string="Is the shifts role one of the current user roles",
        export_string_translation=False,
        compute="_compute_is_users_role",
        search="_search_is_users_role",
    )
    request_to_switch = fields.Boolean(
        string="Has there been a request to switch on this shift slot?",
        export_string_translation=False,
        default=False,
        readonly=True,
    )

    allocation_type = fields.Selection(
        selection=[
            ("planning", "Planning"),
            ("forecast", "Forecast"),
        ],
        compute="_compute_allocation_type",
    )
    allocated_hours = fields.Float(
        string="Allocated Time",
        compute="_compute_allocated_hours",
        store=True,
        readonly=False,
    )
    allocated_percentage = fields.Float(
        string="Allocated Time %",
        compute="_compute_allocated_percentage",
        default=100,
        store=True,
        readonly=False,
        aggregator="avg",
    )
    duration = fields.Float(compute="_compute_slot_duration")

    publication_warning = fields.Boolean(
        string="Modified Since Last Publication",
        compute="_compute_publication_warning",
        default=False,
        store=True,
        copy=False,
        readonly=True,
        help="If checked, it means that the shift contains has changed since its last publish.",
    )
    state = fields.Selection(
        selection=[
            ("1_draft", "Draft"),
            ("2_published", "Published"),
        ],
        string="Status",
        default="1_draft",
    )
    template_creation = fields.Boolean(
        string="Save as Template",
        inverse="_inverse_template_creation",
        store=False,
    )
    template_autocomplete_ids = fields.Many2many(
        comodel_name="planning.slot.template",
        export_string_translation=False,
        compute="_compute_template_autocomplete_ids",
        store=False,
    )
    template_id = fields.Many2one(
        comodel_name="planning.slot.template",
        string="Shift Templates",
        compute="_compute_template_id",
        store=True,
        readonly=False,
    )
    template_reset = fields.Boolean(export_string_translation=False)
    previous_template_id = fields.Many2one(
        comodel_name="planning.slot.template",
        export_string_translation=False,
    )
    allow_template_creation = fields.Boolean(
        export_string_translation=False,
        compute="_compute_allow_template_creation",
    )

    recurrency_id = fields.Many2one(
        comodel_name="planning.recurrency",
        export_string_translation=False,
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    repeat = fields.Boolean(
        compute="_compute_repeat",
        inverse="_inverse_repeat",
        help="To avoid polluting your database and performance issues, shifts are only created for the next 6 months. They are then gradually created as time passes by in order to always get shifts 6 months ahead. This value can be modified from the settings of Planning, in debug mode.",
    )
    repeat_interval = fields.Integer(
        string="Repeat every",
        compute="_compute_repeat_interval",
        inverse="_inverse_repeat",
        default=1,
    )
    repeat_unit = fields.Selection(
        selection=REPEAT_UNIT_SELECTION,
        compute="_compute_repeat_unit",
        inverse="_inverse_repeat",
        default="week",
        required=True,
    )
    repeat_type = fields.Selection(
        selection=[*REPEAT_TYPE_SELECTION, REPEAT_TYPE_COUNT],
        compute="_compute_repeat_type",
        inverse="_inverse_repeat",
        default="forever",
    )
    repeat_until = fields.Date(
        compute="_compute_repeat_until",
        inverse="_inverse_repeat",
    )
    repeat_number = fields.Integer(
        string="Repetitions",
        compute="_compute_repeat_number",
        inverse="_inverse_repeat",
        default=1,
    )
    recurrence_update = fields.Selection(
        selection=[
            ("this", "This shift"),
            ("subsequent", "This and following shifts"),
            ("all", "All shifts"),
        ],
        default="this",
        store=False,
        copy=False,
    )
    confirm_delete = fields.Boolean(
        export_string_translation=False,
        compute="_compute_confirm_delete",
    )

    is_hatched = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_hatched",
    )

    slot_properties = fields.Properties(
        definition="role_id.slot_properties_definition",
        string="Properties",
        precompute=False,
    )

    _check_start_date_lower_end_date = models.Constraint(
        "CHECK(end_datetime > start_datetime)",
        "The end date of a shift should be after its start date.",
    )
    _check_allocated_hours_positive = models.Constraint(
        "CHECK(allocated_hours >= 0)",
        "Allocated hours and allocated time percentage cannot be negative.",
    )

    @api.depends("role_id.color", "resource_id.color")
    def _compute_color(self) -> None:
        for slot in self:
            slot.color = slot.role_id.color or slot.resource_id.color

    @api.depends("repeat_until")
    def _compute_confirm_delete(self) -> None:
        for slot in self:
            if slot.recurrency_id and slot.repeat_until:
                slot.confirm_delete = (
                    fields.Date.to_date(
                        slot.recurrency_id.slot_ids.sorted("end_datetime")[
                            -1
                        ].end_datetime
                    )
                    > slot.repeat_until
                )
            else:
                slot.confirm_delete = False

    @api.constrains("repeat_until")
    def _check_repeat_until(self) -> None:
        if any(
            slot.repeat_until and slot.repeat_until < slot.start_datetime.date()
            for slot in self
        ):
            raise UserError(
                self.env._(
                    "Uh-oh! Let's keep things in the right order: the recurrence end date should always "
                    "come after the shift start date. It's like trying to eat your breakfast before waking up - not possible!"
                )
            )

    @api.onchange("repeat_until")
    def _onchange_repeat_until(self) -> None:
        self._check_repeat_until()

    @api.depends("resource_id.company_id")
    def _compute_planning_slot_company_id(self) -> None:
        for slot in self:
            slot.company_id = (
                slot.resource_id.company_id or slot.company_id or slot.env.company
            )

    @api.depends("end_datetime")
    def _compute_past_shift(self) -> None:
        now = fields.Datetime.now()
        for slot in self:
            if slot.end_datetime:
                if slot.end_datetime < now:
                    slot.is_past = True
                else:
                    slot.is_past = False
            else:
                slot.is_past = False

    @api.depends("resource_id.employee_id", "resource_type")
    def _compute_employee_id(self) -> None:
        for slot in self:
            slot.employee_id = (
                slot.resource_id.with_context(active_test=False).employee_id
                if slot.resource_type == "human"
                else False
            )

    @api.depends("employee_id", "template_id")
    def _compute_role_id(self) -> None:
        for slot in self:
            if not slot.role_id:
                slot.role_id = slot.resource_id.default_role_id

            if slot.template_id:
                slot.previous_template_id = slot.template_id
                if slot.template_id.role_id:
                    slot.role_id = slot.template_id.role_id
            elif (
                slot.previous_template_id
                and not slot.template_id
                and slot.previous_template_id.role_id == slot.role_id
            ):
                slot.role_id = False

    @api.model
    def _get_scheduled_states(self) -> list:
        return [
            state
            for state in self._fields["state"].get_values(self.env)
            if state != "1_draft"
        ]

    @api.depends("state")
    def _compute_is_hatched(self) -> None:
        for slot in self:
            slot.is_hatched = slot.state == "1_draft"

    @api.depends("role_id")
    def _compute_is_users_role(self) -> None:
        user_resource_roles = (
            self.env["resource.resource"]
            .search([("user_id", "=", self.env.user.id)])
            .role_ids
        )
        for slot in self:
            slot.is_users_role = (
                (slot.role_id in user_resource_roles)
                or not user_resource_roles
                or not slot.role_id
            )

    def _search_is_users_role(self, operator, value):
        if operator != "in":
            return NotImplemented
        user_resource_roles = (
            self.env["resource.resource"]
            .search([("user_id", "=", self.env.user.id)])
            .role_ids
        )
        if not user_resource_roles:
            return [(1, "=", 1)]
        return [
            "|",
            ("role_id", "in", user_resource_roles.ids),
            ("role_id", "=", False),
        ]

    @api.depends("start_datetime", "end_datetime")
    def _compute_allocation_type(self) -> None:
        for slot in self:
            if (
                slot.start_datetime
                and slot.end_datetime
                and slot._get_slot_duration() < 24
            ):
                slot.allocation_type = "planning"
            else:
                slot.allocation_type = "forecast"

    @api.depends("allocated_hours")
    def _compute_allocated_percentage(self) -> None:
        allocated_hours_field = self._fields["allocated_hours"]
        slots = self.filtered(
            lambda slot: (
                not self.env.is_to_compute(allocated_hours_field, slot)
                and slot.start_datetime
                and slot.end_datetime
                and slot.start_datetime != slot.end_datetime
            )
        )
        if not slots:
            return
        start_utc = min(slots.mapped("start_datetime")).replace(tzinfo=UTC)
        end_utc = max(slots.mapped("end_datetime")).replace(tzinfo=UTC)
        schedule = slots.resource_id._get_work_schedule(
            start_utc, end_utc, calendars=slots.company_id.resource_calendar_id
        )
        budgeted = slots._filter_first_served()
        for slot, percentage in budgeted._get_first_served_percentages().items():
            slot.allocated_percentage = percentage
        slots -= budgeted

        for slot in slots:
            if not slot.resource_id and slot.allocation_type == "planning":
                duration = slot._get_slot_duration_capped()
                slot.allocated_percentage = (
                    100 * slot.allocated_hours / duration if duration else 100
                )
            else:
                work_hours = slot._get_working_hours_over_period(
                    start_utc, end_utc, schedule
                )
                slot.allocated_percentage = (
                    100 * slot.allocated_hours / work_hours if work_hours else 100
                )

    @api.depends(
        "start_datetime",
        "end_datetime",
        "resource_id.calendar_id.schedule_type",
        "company_id.resource_calendar_id",
        "allocated_percentage",
    )
    def _compute_allocated_hours(self) -> None:
        percentage_field = self._fields["allocated_percentage"]
        self.env.remove_to_compute(percentage_field, self)
        open_slots = self.filtered(
            lambda s: (
                (s.allocation_type == "planning" or not s.company_id)
                and not s.resource_id
            )
        )
        assigned_slots = self - open_slots
        _debug.logic("allocated_hours_split", open=open_slots, assigned=assigned_slots)
        for slot in open_slots:
            ratio = slot.allocated_percentage / 100.0
            slot.allocated_hours = slot._get_slot_duration_capped() * ratio
        if assigned_slots:
            unplanned_assigned_slots = assigned_slots.filtered_domain(
                [
                    "|",
                    ("start_datetime", "=", False),
                    ("end_datetime", "=", False),
                ]
            )
            for slot in unplanned_assigned_slots:
                slot.allocated_hours = 0.0
            planned_assigned_slots = assigned_slots - unplanned_assigned_slots
            budgeted = planned_assigned_slots._filter_first_served()
            for slot, hours in budgeted._get_first_served_hours().items():
                slot.allocated_hours = hours
            planned_assigned_slots -= budgeted
            if not planned_assigned_slots:
                return
            start_utc = min(planned_assigned_slots.mapped("start_datetime")).replace(
                tzinfo=UTC
            )
            end_utc = max(planned_assigned_slots.mapped("end_datetime")).replace(
                tzinfo=UTC
            )

            schedule = assigned_slots.resource_id._get_work_schedule(
                start_utc,
                end_utc,
                calendars=assigned_slots.company_id.resource_calendar_id,
            )

            slots_by_allocated_hours = defaultdict(lambda: self.env["planning.slot"])
            for slot in planned_assigned_slots:
                allocated_hour = slot._get_duration_over_period(
                    slot.start_datetime.replace(tzinfo=UTC),
                    slot.end_datetime.replace(tzinfo=UTC),
                    schedule,
                    has_allocated_hours=False,
                )
                slots_by_allocated_hours[allocated_hour] |= slot
            for allocated_hours, slots in slots_by_allocated_hours.items():
                slots.allocated_hours = allocated_hours

    @api.depends(
        "start_datetime", "end_datetime", "resource_id", "allocated_percentage"
    )
    def _compute_overlap_slot_count(self) -> None:
        peers_by_slot = self._get_conflicting_slots()
        for slot in self:
            slot.overlap_slot_count = len(peers_by_slot[slot.id])

    @api.depends(
        "start_datetime", "end_datetime", "resource_id", "allocated_percentage"
    )
    def _compute_conflicting_slot_ids(self) -> None:
        peers_by_slot = self._get_conflicting_slots()
        for slot in self:
            slot.conflicting_slot_ids = peers_by_slot[slot.id]

    def _get_conflicting_slots(self):
        is_manager = self.env.user.has_group("planning.group_planning_manager")
        with _debug.perf("conflicts", cr=self.env.cr, slots=self) as span:
            conflicts_by_slot = self._get_schedule_conflicts_batch()
            span.set(with_conflicts=sum(1 for v in conflicts_by_slot.values() if v))
        peers_by_slot = {}
        _debug.logic("conflict_visibility", manager=is_manager, slots=self)
        for slot in self:
            peers = self.browse(
                [
                    reservation.res_id
                    for reservation in conflicts_by_slot[slot.id]
                    if reservation.res_model == "planning.slot"
                ]
            ).exists()
            if not is_manager:
                peers = self.search(
                    [("id", "in", peers.ids), ("state", "!=", "1_draft")]
                )
            peers_by_slot[slot.id] = peers
        return peers_by_slot

    @api.model
    def _search_overlap_slot_count(self, operator, value):
        if operator == "in":
            return Domain.OR(self._search_overlap_slot_count("=", v) for v in value)
        if operator not in ["=", ">"] or not isinstance(value, int) or value != 0:
            raise NotImplementedError(
                "Operation not supported, you should always compare overlap_slot_count to 0 value with = or > operator."
            )

        conflicted = (
            self.env["resource.reservation"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "planning.slot"),
                    ("schedule_overlap_count", ">", 0),
                ]
            )
        )
        slot_ids = list({reservation.res_id for reservation in conflicted})
        return [("id", "in" if operator == ">" else "not in", slot_ids)]


    def _get_fields_reservation_date(self) -> tuple:
        return ("start_datetime", "end_datetime")

    def _filter_first_served(self):
        if self.env.context.get("planning_print_pill"):
            return self.browse()
        return self.filtered(
            lambda slot: (
                slot.resource_id
                and slot.start_datetime
                and slot.end_datetime
                and slot.start_datetime < slot.end_datetime
                and slot.resource_id._is_flexible()
                and not slot.resource_id._is_fully_flexible()
            )
        )

    def _recompute_first_served_hours(self) -> None:
        self.env.add_to_compute(
            self._fields["allocated_hours"], self._filter_first_served()
        )

    def _get_first_served_claims(self) -> list:
        return [
            FirstServedClaim(
                key=slot,
                resource=slot.resource_id,
                start=slot.start_datetime,
                stop=slot.end_datetime,
                percentage=slot.allocated_percentage,
                order_id=slot._origin.reservation_ids[:1].id or None,
                consumes=True,
            )
            for slot in self
        ]

    def _get_first_served_hours(self) -> dict:
        return self.env["resource.reservation"]._get_first_served_hours_of(
            self._get_first_served_claims(),
            ignore_ids=self._origin.reservation_ids.ids,
        )

    def _get_first_served_days(self) -> dict:
        return self.env["resource.reservation"]._get_first_served_days_of(
            self._get_first_served_claims(),
            ignore_ids=self._origin.reservation_ids.ids,
        )

    def _get_first_served_percentages(self) -> dict:
        return self.env["resource.reservation"]._get_first_served_percentages_of(
            self._get_first_served_claims(),
            {slot: slot.allocated_hours for slot in self},
            ignore_ids=self._origin.reservation_ids.ids,
        )

    def _prepare_reservation_vals_list(self):
        self.check_singleton()
        if not self.start_datetime or not self.end_datetime or not self.resource_id:
            return []
        return [
            {
                "name": self.name or self.role_id.display_name or self.env._("Shift"),
                "date_start": self.start_datetime,
                "date_end": self.end_datetime,
                "resource_id": self.resource_id.id,
                "allocated_percentage": max(0.0, self.allocated_percentage),
                "enforcement_mode": "soft",
            }
        ]

    def _get_fields_sync_trigger(self):
        return super()._get_fields_sync_trigger() | {
            "resource_id",
            "name",
            "role_id",
            "allocated_hours",
            "allocated_percentage",
        }

    @api.depends("start_datetime", "end_datetime")
    def _compute_slot_duration(self) -> None:
        for slot in self:
            slot.duration = slot._get_slot_duration()

    def _filtered_assigned_or_during(self, intervals) -> Self:
        return self.filtered(
            lambda s: (
                s.employee_id
                or any(
                    s.start_datetime.replace(tzinfo=UTC) < end
                    and s.end_datetime.replace(tzinfo=UTC) > start
                    for start, end, _dummy in intervals
                )
            )
        )

    def _get_slot_duration(self):
        self.check_singleton()
        resource = self.resource_id
        if not self.start_datetime or not self.end_datetime:
            return False

        if resource:
            start = self.start_datetime.replace(tzinfo=UTC).astimezone(
                timezone(resource.tz)
            )
            end = self.end_datetime.replace(tzinfo=UTC).astimezone(
                timezone(resource.tz)
            )
            return resource._get_work_schedule(start, end).work_hours(resource)
        return (self.end_datetime - self.start_datetime).total_seconds() / 3600.0

    def _get_domain_template_slots(self):
        domain = []
        roles = self.resource_id.role_ids
        if self.role_id:
            roles |= self.role_id
        if roles:
            domain += ["|", ("role_id", "in", roles.ids), ("role_id", "=", False)]
        return domain

    @api.depends("role_id", "employee_id")
    def _compute_template_autocomplete_ids(self) -> None:
        for slot in self:
            domain = slot._get_domain_template_slots()
            templates = self.env["planning.slot.template"].search(
                domain, order="start_time", limit=10
            )
            slot.template_autocomplete_ids = templates + slot.template_id

    @api.depends("employee_id", "role_id", "start_datetime", "end_datetime")
    def _compute_template_id(self):
        for slot in self.filtered(lambda s: s.template_id):
            slot.previous_template_id = slot.template_id
            slot.template_reset = False
            if slot._different_than_template():
                slot.template_id = False
                slot.previous_template_id = False
                slot.template_reset = True

    def _different_than_template(self, check_empty=True) -> bool:
        self.check_singleton()
        if not (self.start_datetime and self.end_datetime):
            return True
        template_fields = self._get_fields_template().items()
        for template_field, slot_field in template_fields:
            if self.template_id[template_field] or not check_empty:
                if template_field in ("start_time", "end_time"):
                    h = int(self.template_id[template_field])
                    m = round(modf(self.template_id[template_field])[0] * 60.0)
                    slot_time = self[slot_field].astimezone(timezone(self._get_tz()))
                    if slot_time.hour != h or slot_time.minute != m:
                        return True
                elif template_field == "duration_days":
                    if (
                        self.start_datetime
                        and self.end_datetime
                        and days_span(self.start_datetime, self.end_datetime)
                        != self.template_id[template_field]
                    ):
                        return True
                elif self[slot_field] != self.template_id[template_field]:
                    return True

        return False

    @api.depends(
        "template_id", "role_id", "allocated_hours", "start_datetime", "end_datetime"
    )
    def _compute_allow_template_creation(self) -> None:
        for slot in self:
            if not (slot.start_datetime and slot.end_datetime):
                slot.allow_template_creation = False
                continue

            values = slot._prepare_template_values()
            domain = [(x, "=", values[x]) for x in values]
            existing_templates = self.env["planning.slot.template"].search(
                domain, limit=1
            )
            slot.allow_template_creation = (
                not existing_templates
                and slot._different_than_template(check_empty=False)
            )

    @api.depends("recurrency_id")
    def _compute_repeat(self) -> None:
        for slot in self:
            if slot.recurrency_id:
                slot.repeat = True
            else:
                slot.repeat = False

    @api.depends("recurrency_id.repeat_interval")
    def _compute_repeat_interval(self) -> None:
        recurrency_slots = self.filtered("recurrency_id")
        for slot in recurrency_slots:
            if slot.recurrency_id:
                slot.repeat_interval = slot.recurrency_id.repeat_interval
        (self - recurrency_slots).update(self.default_get(["repeat_interval"]))

    def _get_recurrence_tz(self):
        self.check_singleton()
        return timezone(self.company_id.resource_calendar_id.tz or "UTC")

    @api.depends("recurrency_id.repeat_until", "repeat", "repeat_type")
    def _compute_repeat_until(self) -> None:
        for slot in self:
            repeat_until = False
            if slot.repeat and slot.repeat_type == "until":
                if slot.recurrency_id and slot.recurrency_id.repeat_until:
                    repeat_until = (
                        slot.recurrency_id.repeat_until.replace(tzinfo=UTC)
                        .astimezone(slot._get_recurrence_tz())
                        .date()
                    )
                elif slot.start_datetime:
                    repeat_until = (
                        (slot.start_datetime + relativedelta(weeks=1))
                        .replace(tzinfo=UTC)
                        .astimezone(slot._get_recurrence_tz())
                        .date()
                    )
            slot.repeat_until = repeat_until

    @api.depends("recurrency_id.repeat_number", "repeat_type")
    def _compute_repeat_number(self) -> None:
        recurrency_slots = self.filtered("recurrency_id")
        for slot in recurrency_slots:
            slot.repeat_number = slot.recurrency_id.repeat_number
        (self - recurrency_slots).update(self.default_get(["repeat_number"]))

    @api.depends("recurrency_id.repeat_unit")
    def _compute_repeat_unit(self) -> None:
        non_recurrent_slots = self.env["planning.slot"]
        for slot in self:
            if slot.recurrency_id:
                slot.repeat_unit = slot.recurrency_id.repeat_unit
            else:
                non_recurrent_slots += slot
        non_recurrent_slots.update(self.default_get(["repeat_unit"]))

    @api.depends("recurrency_id.repeat_type")
    def _compute_repeat_type(self) -> None:
        recurrency_slots = self.filtered("recurrency_id")
        for slot in recurrency_slots:
            if slot.recurrency_id:
                slot.repeat_type = slot.recurrency_id.repeat_type
        (self - recurrency_slots).update(self.default_get(["repeat_type"]))

    def _inverse_repeat(self) -> None:
        for slot in self:
            if slot.repeat and not slot.recurrency_id.id:
                repeat_until = False
                repeat_number = 0
                if slot.repeat_type == "until":
                    repeat_until = datetime.combine(
                        fields.Date.to_date(slot.repeat_until), datetime.max.time()
                    )
                    repeat_until = (
                        repeat_until.replace(tzinfo=slot._get_recurrence_tz())
                        .astimezone(UTC)
                        .replace(tzinfo=None)
                    )
                if slot.repeat_type == "count":
                    repeat_number = slot.repeat_number
                recurrency_values = {
                    "repeat_interval": slot.repeat_interval,
                    "repeat_unit": slot.repeat_unit,
                    "repeat_until": repeat_until,
                    "repeat_number": repeat_number,
                    "repeat_type": slot.repeat_type,
                    "company_id": slot.company_id.id,
                }
                recurrence = self.env["planning.recurrency"].create(recurrency_values)
                slot.recurrency_id = recurrence
            elif not slot.repeat and slot.recurrency_id.id:
                slot.recurrency_id._remove_slot(slot.end_datetime)
                slot.recurrency_id.unlink()

    def _inverse_template_creation(self) -> None:
        PlanningTemplate = self.env["planning.slot.template"]
        for slot in self.filtered(lambda s: s.template_creation):
            values = slot._prepare_template_values()
            domain = [(x, "=", values[x]) for x in values]
            existing_templates = PlanningTemplate.search(domain, limit=1)
            if not existing_templates:
                template = PlanningTemplate.create(values)
                slot.write(
                    {"template_id": template.id, "previous_template_id": template.id}
                )
            else:
                slot.write({"template_id": existing_templates.id})

    def _get_non_working_days_bounds(
        self, start_datetime, end_datetime, resource=False
    ) -> tuple:
        resource = resource or self.env.user.employee_id.resource_id
        user_tz = timezone(
            self.env.user.tz
            or (resource.employee_id and resource.employee_id.tz)
            or resource.tz
            or self.env.context.get("tz")
            or self.env.user.company_id.resource_calendar_id.tz
            or "UTC"
        )
        start_date_in_user_tz = start_datetime.astimezone(user_tz)
        offset = start_date_in_user_tz.utcoffset().total_seconds() / 3600
        return (
            (
                start_datetime.replace(
                    hour=0, minute=0, second=0, microsecond=0, tzinfo=None
                )
                + timedelta(hours=8 - offset)
            ),
            (
                end_datetime.replace(
                    hour=0, minute=0, second=0, microsecond=0, tzinfo=None
                )
                + timedelta(hours=17 - offset)
            ),
        )

    @api.model
    def _get_start_end_dates(
        self,
        start_datetime,
        end_datetime,
        resource_id,
        template_id,
        previous_template_id,
        template_reset,
    ):

        def convert_datetime_timezone(dt, tz):
            return dt and dt.replace(tzinfo=UTC).astimezone(tz)

        resource = resource_id or self.env.user.employee_id.resource_id
        company = self.company_id or self.env.company
        employee = resource_id.employee_id if resource_id.type == "human" else False
        user_tz = timezone(
            self.env.user.tz
            or (employee and employee.tz)
            or resource_id.tz
            or self.env.context.get("tz")
            or self.env.user.company_id.resource_calendar_id.tz
            or "UTC"
        )

        intervals = []
        start = (
            convert_datetime_timezone(start_datetime, user_tz)
            if start_datetime
            else self._get_default_start_datetime().replace(tzinfo=user_tz)
        )
        end = (
            convert_datetime_timezone(end_datetime, user_tz)
            if end_datetime
            else self._get_default_end_datetime().replace(tzinfo=user_tz)
        )

        if not template_id:
            calendar_id = (
                company.resource_calendar_id
                if not resource or resource._is_fully_flexible()
                else resource.calendar_id
            )
            work_interval = calendar_id._work_intervals_batch(start, end)[False]
            intervals = [
                (date_start, date_stop)
                for date_start, date_stop, attendance in work_interval
            ]
            if not intervals and not self.env.context.get(
                "planning_keep_default_datetime", False
            ):
                return self._get_non_working_days_bounds(start, end, resource)

        start = (
            convert_datetime_timezone(start_datetime, user_tz)
            if start_datetime
            else self._get_default_start_datetime().replace(tzinfo=user_tz)
        )
        end = (
            convert_datetime_timezone(end_datetime, user_tz)
            if end_datetime
            else self._get_default_end_datetime().replace(tzinfo=user_tz)
        )

        if resource and intervals:
            start = (
                intervals[0][0]
                .replace(tzinfo=None)
                .replace(tzinfo=timezone(resource.tz))
            )
            end = (
                intervals[-1][-1]
                .replace(tzinfo=None)
                .replace(tzinfo=timezone(resource.tz))
            )

        if not previous_template_id and not template_reset:
            start = start.astimezone(UTC).replace(tzinfo=None)
            end = end.astimezone(UTC).replace(tzinfo=None)

        if template_id and start_datetime:
            h = int(template_id.start_time)
            m = round(modf(template_id.start_time)[0] * 60.0)
            start = start_datetime.replace(tzinfo=UTC).astimezone(
                timezone(resource.tz) if resource else user_tz
            )
            start = start.replace(hour=int(h), minute=int(m))

            h = int(template_id.end_time)
            m = round(modf(template_id.end_time)[0] * 60.0)
            end = start + relativedelta(
                days=(template_id.duration_days - 1), hour=0, minute=0, second=0
            )
            if template_id.duration_days > 1 and resource_id.calendar_id:
                end = resource.calendar_id.plan_days(
                    template_id.duration_days, start, compute_leaves=True
                )
            end = end.replace(hour=int(h), minute=int(m))

            if resource and not resource._is_flexible():
                work_interval, _dummy = resource._get_valid_work_intervals(start, end)
                start = start.astimezone(UTC).replace(tzinfo=None)
                end = (
                    work_interval[resource.id]
                    ._items[-1][1]
                    .astimezone(UTC)
                    .replace(tzinfo=None)
                    if work_interval[resource.id]._items
                    else end
                )

        start = start.astimezone(UTC).replace(tzinfo=None) if start.tzinfo else start
        end = end.astimezone(UTC).replace(tzinfo=None) if end.tzinfo else end
        return (start, end)

    @api.depends("template_id")
    def _compute_datetime(self) -> None:
        for slot in self.filtered(lambda s: s.template_id):
            slot.start_datetime, slot.end_datetime = self._get_start_end_dates(
                slot.start_datetime,
                slot.end_datetime,
                slot.resource_id,
                slot.template_id,
                slot.previous_template_id,
                slot.template_reset,
            )

    @api.depends(lambda self: self._get_fields_breaking_publication())
    def _compute_publication_warning(self) -> None:
        for slot in self:
            slot.publication_warning = (
                slot.resource_id
                and slot.resource_type == "human"
                and slot.state == "2_published"
            )

    def _company_working_hours(self, start, end) -> tuple:
        company = self.company_id or self.env.company
        work_interval = company.resource_calendar_id._work_intervals_batch(start, end)[
            False
        ]
        intervals = [
            (date_start, date_stop)
            for date_start, date_stop, attendance in work_interval
        ]

        if not intervals:
            return ()

        start_datetime, end_datetime = (start, end)
        if (
            intervals and (end_datetime - start_datetime).days == 0
        ):
            start_datetime = intervals[0][0]
            end_datetime = [
                stop
                for start, stop in intervals
                if last_day_of(start, stop) == start_datetime.date()
            ][-1]
        elif intervals and (end_datetime - start_datetime).days > 0:
            start_datetime = intervals[0][0]
            end_datetime = intervals[-1][1]

        return (start_datetime, end_datetime)

    def _compute_allow_self_unassign(self) -> None:
        allow_self_unassign_planning = self.filtered(
            lambda p: p.company_id.planning_employee_unavailabilities == "unassign"
        )
        allow_self_unassign_planning.allow_self_unassign = True
        (self - allow_self_unassign_planning).allow_self_unassign = False

    @api.depends("self_unassign_days_before", "start_datetime")
    def _compute_unassign_deadline(self) -> None:
        slots_with_date = self.filtered("start_datetime")
        (self - slots_with_date).unassign_deadline = False
        for slot in slots_with_date:
            slot.unassign_deadline = fields.Datetime.subtract(
                slot.start_datetime, days=slot.self_unassign_days_before
            )

    @api.depends("unassign_deadline")
    def _compute_is_unassign_deadline_passed(self) -> None:
        slots_with_date = self.filtered("unassign_deadline")
        (self - slots_with_date).is_unassign_deadline_passed = False
        for slot in slots_with_date:
            slot.is_unassign_deadline_passed = (
                slot.unassign_deadline < fields.Datetime.now()
            )


    @api.model
    def _read_group_fields_nullify(self):
        return []

    @api.model
    def formatted_read_group(
        self,
        domain,
        groupby=(),
        aggregates=(),
        having=(),
        offset=0,
        limit=None,
        order=None,
    ) -> list[dict]:
        res = super().formatted_read_group(
            domain, groupby, aggregates, having, offset, limit, order
        )
        for aggregate_nullify in self._read_group_fields_nullify():
            if aggregate_nullify not in aggregates:
                continue
            for row in res:
                if row[aggregate_nullify] == 0:
                    row[aggregate_nullify] = False
        return res

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)

        if res.get("resource_id"):
            resource_id = self.env["resource.resource"].browse(res.get("resource_id"))
            template_id, previous_template_id = [
                res.get(key) for key in ["template_id", "previous_template_id"]
            ]
            template_id = template_id and self.env["planning.slot.template"].browse(
                template_id
            )
            previous_template_id = template_id and self.env[
                "planning.slot.template"
            ].browse(previous_template_id)
            res["start_datetime"], res["end_datetime"] = self._get_start_end_dates(
                res.get("start_datetime"),
                res.get("end_datetime"),
                resource_id,
                template_id,
                previous_template_id,
                res.get("template_reset"),
            )
        elif "start_datetime" in fields and not self.env.context.get(
            "planning_keep_default_datetime", False
        ):
            start_datetime = (
                Datetime.to_datetime(res.get("start_datetime"))
                if res.get("start_datetime")
                else self._get_default_start_datetime()
            )
            end_datetime = (
                Datetime.to_datetime(res.get("end_datetime"))
                if res.get("end_datetime")
                else self._get_default_end_datetime()
            )
            start = start_datetime.replace(tzinfo=UTC)
            end = (
                end_datetime.replace(tzinfo=UTC)
                if end_datetime
                else self._get_default_end_datetime()
            )
            opening_hours = self._company_working_hours(start, end)
            if opening_hours:
                res["start_datetime"] = (
                    opening_hours[0].astimezone(UTC).replace(tzinfo=None)
                )
                if "end_datetime" in fields:
                    res["end_datetime"] = (
                        opening_hours[1].astimezone(UTC).replace(tzinfo=None)
                    )
            else:
                res["start_datetime"], end_datetime = self._get_non_working_days_bounds(
                    start_datetime, end_datetime
                )
                if "end_datetime" in fields:
                    res["end_datetime"] = end_datetime

        return res

    @api.depends(lambda self: self._display_name_fields())
    @api.depends_context("group_by")
    def _compute_display_name(self):
        group_by = self.env.context.get("group_by", [])
        field_list = [
            fname for fname in self._display_name_fields() if fname not in group_by
        ]

        self = self.sudo()
        for slot in self.with_context(hide_partner_ref=True):
            name_values = [
                self._fields[fname].convert_to_display_name(slot[fname], slot)
                if fname != "resource_id"
                else slot.resource_id.name
                for fname in field_list
                if slot[fname]
                and not (fname == "resource_id" and slot.resource_type == "human")
            ][:4]
            name = " - ".join(name_values)

            if slot.name:
                name = f"{name} \U0001f4ac"

            slot.display_name = name or ""

    @api.model_create_multi
    def create(self, vals_list):
        Resource = self.env["resource.resource"]
        _debug.lifecycle(
            "create",
            count=len(vals_list),
            multi=bool(self.env.context.get("multi_create")),
        )
        for vals in vals_list:
            if vals.get("resource_id"):
                resource = Resource.browse(vals.get("resource_id"))
                if not vals.get("company_id"):
                    vals["company_id"] = resource.company_id.id
                if resource.type != "human":
                    vals["state"] = "2_published"
            if not vals.get("company_id"):
                vals["company_id"] = self.env.company.id
        if self.env.context.get("multi_create"):
            vals_list_updated = []
            resource_per_id = {}
            user_tz = timezone(self._get_tz())
            min_datetime = fields.Datetime.from_string(
                vals_list[0]["start_datetime"]
            ).astimezone(user_tz)
            max_datetime = fields.Datetime.from_string(
                vals_list[-1]["end_datetime"]
            ).astimezone(user_tz)
            for vals in vals_list:
                if resource_id := vals.get("resource_id"):
                    resource = resource_per_id.get(resource_id)
                    if not resource:
                        resource = Resource.browse(resource_id)
                        resource_per_id[resource_id] = resource
                        Resource |= resource
            schedule, _ = Resource._get_valid_work_intervals(min_datetime, max_datetime)
            for vals in vals_list:
                if resource_id := vals.get("resource_id"):
                    shift_interval = Intervals(
                        [
                            (
                                fields.Datetime.from_string(
                                    vals.get("start_datetime")
                                ).astimezone(user_tz),
                                fields.Datetime.from_string(
                                    vals.get("end_datetime")
                                ).astimezone(user_tz),
                                self.env["resource.calendar.attendance"],
                            )
                        ]
                    )
                    if shift_interval & schedule[resource_id]:
                        vals_list_updated.append(vals)
            if vals_list_updated:
                vals_list = vals_list_updated
        slots = super().create(vals_list)
        slots.flush_recordset()
        slots.browse(
            [
                slot.id
                for slot, values in zip(slots, vals_list, strict=True)
                if "allocated_hours" in values and "allocated_percentage" not in values
            ]
        )._compute_allocated_percentage()
        slots._active_for_sync()._sync_reservations()
        recurrences = self.env["planning.recurrency"]
        for slot, values in zip(slots, vals_list, strict=True):
            if slot.repeat and not values.get("recurrency_id"):
                recurrences |= slot.recurrency_id
        recurrences._repeat_slot()
        return slots

    def create_batch_from_calendar(self, vals_list) -> Self | None:
        if not len(vals_list):
            return None
        template_id = self.env["planning.slot.template"].browse(
            vals_list[0]["template_id"]
        )

        resources = self.env["resource.resource"]
        resource_per_id = {}
        min_datetime = datetime.strptime(
            vals_list[0]["start_datetime"], "%Y-%m-%d %H:%M:%S"
        )
        max_datetime = datetime.strptime(
            vals_list[-1]["end_datetime"], "%Y-%m-%d %H:%M:%S"
        )
        if template_id.duration_days > 1:
            max_datetime += relativedelta(months=2)

        for vals in vals_list:
            if resource_id := vals.get("resource_id"):
                resource = resource_per_id.get(resource_id)
                if not resource:
                    resource = resources.browse(resource_id)
                    resource_per_id[resource_id] = resource
                    resources |= resource

        user_tz = timezone(self._get_tz())
        schedule, _ = resources._get_valid_work_intervals(
            min_datetime.astimezone(user_tz), max_datetime.astimezone(user_tz)
        )
        vals_list_updated_slots = []
        if template_id.duration_days > 1:
            for vals in vals_list:
                if resource_id := vals.get("resource_id"):
                    end_datetime = datetime.strptime(
                        vals["end_datetime"], "%Y-%m-%d %H:%M:%S"
                    )
                    current_end_datetime = end_datetime - relativedelta(
                        days=template_id.duration_days
                    )
                    current_start_datetime = datetime.strptime(
                        vals["start_datetime"], "%Y-%m-%d %H:%M:%S"
                    ) - relativedelta(days=1)
                    working_days_to_assign = template_id.duration_days
                    while (
                        working_days_to_assign > 0
                        and current_end_datetime < max_datetime
                    ):
                        current_start_datetime += relativedelta(days=1)
                        current_end_datetime += relativedelta(days=1)
                        shift_interval = Intervals(
                            [
                                (
                                    current_start_datetime.astimezone(user_tz),
                                    current_end_datetime.astimezone(user_tz),
                                    self.env["resource.calendar.attendance"],
                                )
                            ]
                        )
                        if shift_interval & schedule[resource_id]:
                            working_days_to_assign -= 1

                    vals["end_datetime"] = current_end_datetime.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    vals_list_updated_slots.append(vals)
                else:
                    vals_list_updated_slots = vals_list
                    break
        else:
            for vals in vals_list:
                if resource_id := vals.get("resource_id"):
                    shift_interval = Intervals(
                        [
                            (
                                datetime.strptime(
                                    vals["start_datetime"], "%Y-%m-%d %H:%M:%S"
                                ).astimezone(user_tz),
                                datetime.strptime(
                                    vals["end_datetime"], "%Y-%m-%d %H:%M:%S"
                                ).astimezone(user_tz),
                                self.env["resource.calendar.attendance"],
                            )
                        ]
                    )
                    if shift_interval & schedule[resource_id]:
                        vals_list_updated_slots.append(vals)
                else:
                    vals_list_updated_slots.append(vals)

        return self.create(vals_list_updated_slots)

    def write(self, vals):
        values = vals
        _debug.lifecycle("write", slots=self, fields=list(vals))
        new_resource = (
            self.env["resource.resource"].browse(values["resource_id"])
            if "resource_id" in values
            else None
        )
        if new_resource and new_resource.type != "human":
            values["state"] = "2_published"
        for slot in self.filtered(
            lambda s: (
                new_resource
                and s.state == "2_published"
                and s.resource_type == "human"
                and new_resource.type == "human"
            )
        ):
            _debug.pipeline(
                "shift_reassigned",
                slot=slot,
                was=slot.resource_id,
                now=new_resource,
            )
            self._send_shift_assigned(slot, new_resource)
        slots_clearing_request_to_switch = self.filtered(
            lambda s: (
                s.request_to_switch
                and (
                    (new_resource and s.resource_id != new_resource)
                    or (
                        "start_datetime" in values
                        and s.start_datetime != values["start_datetime"]
                    )
                    or (
                        "end_datetime" in values
                        and s.end_datetime != values["end_datetime"]
                    )
                )
            )
        )

        recurrence_update = values.pop("recurrence_update", "this")
        shifts_to_update = self
        if shifts_to_update.recurrency_id and recurrence_update != "this":
            shifts_to_update.check_singleton()
            datetime_keys = values.keys() & {"start_datetime", "end_datetime"}
            if recurrence_update == "subsequent":
                subsequent_slots = self.search(
                    [
                        "&",
                        ("recurrency_id", "=", shifts_to_update.recurrency_id.id),
                        ("start_datetime", ">", shifts_to_update.start_datetime),
                    ]
                )
                if datetime_keys:
                    if "start_datetime" in datetime_keys:
                        shifts_to_update.recurrency_id.date_recurrence_origin = False
                    values["repeat_type"] = self.repeat_type
                    values["repeat_number"] = 1 + len(subsequent_slots)
                    (
                        shifts_to_update.recurrency_id.slot_ids
                        - subsequent_slots
                        - shifts_to_update
                    ).recurrency_id = False
                    subsequent_slots.unlink()
                else:
                    shifts_to_update |= subsequent_slots
            else:
                all_slots = shifts_to_update.recurrency_id.slot_ids.sorted(
                    "start_datetime"
                )
                if datetime_keys:
                    if "start_datetime" in datetime_keys:
                        shifts_to_update.recurrency_id.date_recurrence_origin = False
                    first_slot = all_slots[0]
                    values.update(
                        {
                            datetime_key: fields.Datetime.from_string(
                                values[datetime_key]
                            )
                            - (self[datetime_key] - first_slot[datetime_key])
                            for datetime_key in datetime_keys
                        }
                    )
                    values["repeat_type"] = (
                        first_slot.repeat_type
                    )
                    (all_slots - first_slot).unlink()
                    shifts_to_update = first_slot
                else:
                    shifts_to_update |= all_slots

        previous_recurrences = shifts_to_update.recurrency_id
        result = super(PlanningSlot, shifts_to_update).write(values)
        if {"end_datetime", "template_id"} & values.keys():
            self.env["access.link"]._sync_record_expiries(shifts_to_update)
        recurrences_to_generate = self.env["planning.recurrency"]
        if values.get("repeat"):
            recurrences_to_generate = (
                shifts_to_update.recurrency_id - previous_recurrences
            )
        if slots_clearing_request_to_switch:
            (slots_clearing_request_to_switch & self.exists()).write(
                {"request_to_switch": False}
            )
        if any(
            key
            in (
                "repeat",
                "repeat_unit",
                "repeat_type",
                "repeat_until",
                "repeat_interval",
                "repeat_number",
            )
            for key in values
        ):
            for slot in shifts_to_update:
                recurrence = slot.recurrency_id
                if recurrence and values.get("repeat") is None:
                    repeat_type = values.get("repeat_type") or recurrence.repeat_type
                    repeat_until = values.get("repeat_until") or recurrence.repeat_until
                    repeat_number = values.get("repeat_number", 0) or slot.repeat_number
                    if repeat_type == "until":
                        repeat_until = datetime.combine(
                            fields.Date.to_date(repeat_until), datetime.max.time()
                        )
                        repeat_until = (
                            repeat_until.replace(
                                tzinfo=timezone(
                                    slot.company_id.resource_calendar_id.tz or "UTC"
                                )
                            )
                            .astimezone(UTC)
                            .replace(tzinfo=None)
                        )
                    recurrency_values = {
                        "repeat_interval": values.get("repeat_interval")
                        or recurrence.repeat_interval,
                        "repeat_unit": values.get("repeat_unit")
                        or recurrence.repeat_unit,
                        "repeat_until": repeat_until
                        if repeat_type == "until"
                        else False,
                        "repeat_number": repeat_number,
                        "repeat_type": repeat_type,
                        "company_id": slot.company_id.id,
                    }
                    recurrence.write(recurrency_values)
                    if slot.repeat_type == "count":
                        final_slot = min(repeat_number, len(recurrence.slot_ids))
                        recurrency_values["repeat_until"] = recurrence.slot_ids.sorted(
                            "end_datetime"
                        )[final_slot - 1].end_datetime
                    end_datetime = (
                        slot.end_datetime
                        if values.get("repeat_unit")
                        else recurrency_values.get("repeat_until")
                    )
                    recurrence._remove_slot(end_datetime)
                    recurrences_to_generate |= recurrence

        triggers = self._get_fields_sync_trigger()
        if triggers.intersection(values.keys()) or values.get("active"):
            to_sync = shifts_to_update.exists()._active_for_sync()
            to_sync.flush_recordset()
            to_sync._sync_reservations()
        recurrences_to_generate.exists()._repeat_slot()
        return result

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        active_resources = self.env["resource.resource"]
        planning_split_tool = self.env.context.get("planning_split_tool")
        check_resource_active = not (
            (default and "resource_id" in default) or planning_split_tool
        )
        if check_resource_active:
            active_resources = self.resource_id.filtered("active")
        for planning, vals in zip(self, vals_list, strict=False):
            if planning_split_tool:
                vals["state"] = planning.state
            if (
                check_resource_active
                and planning.resource_id
                and planning.resource_id not in active_resources
            ):
                vals["resource_id"] = False
        return vals_list

    def copy(self, default=None):
        result = super().copy(default=default)
        if default and {"start_datetime", "resource_id"} & default.keys():
            result._compute_allocated_hours()
        return result

    def split_pill(self, values):

        result = self.copy({"start_datetime": values.get("start_datetime")})
        self.write({"end_datetime": values.get("end_datetime")})
        return result.id


    def action_address_recurrency(self, recurrence_update) -> None:
        if recurrence_update == "this":
            return
        domain = Domain("id", "not in", self.ids)
        if recurrence_update == "all":
            domain &= Domain("recurrency_id", "in", self.recurrency_id.ids)
        elif recurrence_update == "subsequent":
            start_date_per_recurrency_id = {}
            for shift in self:
                if (
                    shift.recurrency_id.id not in start_date_per_recurrency_id
                    or shift.start_datetime
                    < start_date_per_recurrency_id[shift.recurrency_id.id]
                ):
                    start_date_per_recurrency_id[shift.recurrency_id.id] = (
                        shift.start_datetime
                    )
            domain &= Domain.OR(
                Domain("recurrency_id", "=", recurrency_id)
                & Domain("start_datetime", ">", start_datetime)
                for recurrency_id, start_datetime in start_date_per_recurrency_id.items()
            )
        sibling_slots = self.env["planning.slot"].search(domain)
        self.recurrency_id.unlink()
        sibling_slots.unlink()

    def action_unlink(self):
        self.unlink()
        return {"type": "ir.actions.act_window_close"}

    def action_see_overlaping_slots(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "planning.slot",
            "name": self.env._("Shifts in Conflict"),
            "views": [[False, "gantt"], [False, "list"], [False, "form"]],
            "context": {
                "initialDate": min(self.mapped("start_datetime")),
                "search_default_conflict_shifts": True,
                "search_default_resource_id": self.resource_id.ids,
            },
        }

    def action_self_assign(self):
        self.check_singleton()
        if not self.has_access("read"):
            _debug.logic("self_assign_refused", reason="no_read", slot=self)
            raise AccessError(
                self.env._("You don't have the right to assign yourself to shifts.")
            )
        if self.resource_id and not self.request_to_switch:
            _debug.logic("self_assign_refused", reason="already_assigned", slot=self)
            raise UserError(
                self.env._("You can not assign yourself to an already assigned shift.")
            )
        if self.is_past:
            if self.request_to_switch:
                self.sudo().write({"request_to_switch": False})
            _debug.logic("self_assign_refused", reason="past_shift", slot=self)
            raise UserError(
                self.env._("You cannot assign yourself to a shift in the past.")
            )
        if self.company_id in self.env.user.employee_ids.mapped("company_id"):
            resource_id = self.env.user.employee_ids.filtered(
                lambda e: e.company_id == self.company_id
            )[0].resource_id.id
        elif len(self.env.user.employee_ids) == 1:
            resource_id = self.env.user.employee_ids.resource_id.id
        else:
            _debug.logic(
                "self_assign_refused",
                reason="other_company",
                slot=self,
                company=self.company_id,
            )
            raise UserError(
                self.env._(
                    "You cannot assign yourself to a shift belonging to another company."
                )
            )
        _debug.lifecycle("self_assigned", slot=self, resource=resource_id)
        return self.sudo().write({"resource_id": resource_id})

    def action_self_unassign(self):
        self.check_singleton()
        if not self.allow_self_unassign:
            _debug.logic("self_unassign_refused", reason="not_allowed", slot=self)
            raise UserError(
                self.env._(
                    "The company does not allow you to unassign yourself from shifts."
                )
            )
        if self.is_unassign_deadline_passed:
            _debug.logic("self_unassign_refused", reason="deadline", slot=self)
            raise UserError(self.env._("The deadline for unassignment has passed."))
        if self.employee_id not in self.env.user.employee_ids:
            _debug.logic("self_unassign_refused", reason="not_own", slot=self)
            raise UserError(
                self.env._("You can not unassign another employee than yourself.")
            )
        if self.is_past:
            raise UserError(
                self.env._("You cannot unassign yourself from a shift in the past.")
            )
        return self.sudo().write({"resource_id": False})

    def action_switch_shift(self):
        self.check_singleton()
        if not self.has_access("read"):
            raise AccessError(self.env._("You don't have the right to switch shifts."))
        if self.employee_id != self.env.user.employee_id:
            raise UserError(
                self.env._(
                    "You cannot request to switch a shift that is assigned to another user."
                )
            )
        if self.is_past:
            raise UserError(
                self.env._("You cannot switch a shift that is in the past.")
            )
        return self.sudo().write({"request_to_switch": True})

    def action_cancel_switch(self):
        self.check_singleton()
        if not self.has_access("read"):
            raise AccessError(
                self.env._("You don't have the right to cancel a request to switch.")
            )
        if self.employee_id != self.env.user.employee_id:
            raise UserError(
                self.env._(
                    "You cannot cancel a request to switch made by another user."
                )
            )
        if self.is_past:
            raise UserError(
                self.env._("You cannot cancel a request to switch that is in the past.")
            )
        return self.sudo().write({"request_to_switch": False})

    def _append_ics_events(self, calendar: Component, employee_tz: str | None) -> None:
        def ics_datetime(idate):
            tz_info = employee_tz or self.env.user.tz or "UTC"
            return idate and idate.astimezone(timezone(tz_info))

        for slot in self:
            event = calendar.add("vevent")
            if not slot.start_datetime or not slot.end_datetime:
                raise UserError(
                    self.env._("First you have to specify the date of the invitation.")
                )
            event.add("created").value = ics_datetime(fields.Datetime.now())
            event.add("dtstart").value = ics_datetime(slot.start_datetime)
            event.add("dtend").value = ics_datetime(slot.end_datetime)
            event.add("summary").value = slot.display_name
            ics_description_data = {
                "shift": slot._prepare_ics_description_data(),
                "is_google_url": False,
            }
            event.add("description").value = self.env["ir.qweb"]._render(
                "planning.planning_shift_ics_description", ics_description_data
            )

    def _prepare_ics_description_data(self) -> dict:
        return {
            "name": self.name,
            "allocated_hours": self.allocated_hours,
            "allocated_percentage": self.allocated_percentage,
            "role": self.role_id.name,
        }

    def auto_plan_id(self):
        self.check_singleton()
        if not self.with_context(planning_slot_id=self.id).auto_plan_ids(
            [("id", "=", self.id)]
        )["open_shift_assigned"]:
            return self._get_notification_action(
                "danger",
                self.env._("There are no resources available for this open shift."),
            )
        return None

    def _get_open_shifts_resources(self) -> tuple:
        open_shift_role_ids = [shift.role_id.id for shift in self]
        resources = self.env["resource.resource"].search(
            [
                "|",
                ("default_role_id", "in", open_shift_role_ids),
                ("role_ids", "in", self.role_id.ids),
            ]
        )
        resource_ids_per_role = defaultdict(list)
        resource_ids_per_default_role = defaultdict(list)
        for resource in resources:
            resource_ids_per_default_role[resource.default_role_id].append(resource.id)
            for role in resource.role_ids:
                if role != resource.default_role_id:
                    resource_ids_per_role[role].append(resource.id)
        return resources, [resource_ids_per_default_role, resource_ids_per_role]

    def _get_resource_ids_for_assignment(self, resource_dict):
        self.check_singleton()
        resource_ids = resource_dict.get(self.role_id, [])
        shuffle(resource_ids)
        return resource_ids

    @api.model
    def auto_plan_ids(self, view_domain):
        assert self.env.context.get("planning_slot_id") or (
            self.env.context.get("default_start_datetime")
            and self.env.context.get("default_end_datetime")
        ), (
            "`default_start_datetime` and `default_end_datetime` attributes should be in the context"
        )

        open_shifts, min_start, max_end = self._read_group(
            Domain.AND(
                [
                    view_domain,
                    [("resource_id", "=", False)],
                ]
            ),
            [],
            ["id:recordset", "start_datetime:min", "end_datetime:max"],
        )[0]
        if not open_shifts:
            return {"open_shift_assigned": []}
        user_tz = timezone(self.env.user.tz or "UTC")
        min_start = min_start.astimezone(user_tz)
        max_end = max_end.astimezone(user_tz)

        resources, resources_dicts = open_shifts._get_open_shifts_resources()
        flexible_resources = resources.filtered(lambda r: r._is_flexible())
        regular_resources = resources - flexible_resources
        schedule_intervals_per_resource_id, _dummy = (
            regular_resources._get_valid_work_intervals(min_start, max_end)
        )

        (
            flexible_resource_work_intervals,
            flexible_resources_hours_per_day,
            flexible_resources_hours_per_week,
        ) = flexible_resources._get_flexible_resource_valid_work_intervals(
            min_start, max_end
        )
        schedule_intervals_per_resource_id.update(flexible_resource_work_intervals)

        if flexible_resources:
            min_start, max_end = flexible_resources._get_flexible_week_bounds(
                min_start, max_end
            )
        else:
            min_start = min_start.astimezone(UTC) + relativedelta(
                hour=0, minute=0, second=0, microsecond=0
            )
            max_end = max_end.astimezone(UTC) + relativedelta(
                days=1, hour=0, minute=0, second=0, microsecond=0
            )

        min_start = min_start.astimezone(UTC).replace(tzinfo=None)
        max_end = max_end.astimezone(UTC).replace(tzinfo=None)
        PlanningShift = self.env["planning.slot"]
        remaining_hours_per_day = deepcopy(flexible_resources_hours_per_day)
        remaining_hours_per_week = deepcopy(flexible_resources_hours_per_week)
        loads = self.env["resource.reservation"]._get_booking_load_batch(
            resources, min_start, max_end
        )
        booked_hours = flexible_resources._get_flexible_booking_hours_per_day(
            loads, min_start.replace(tzinfo=UTC), max_end.replace(tzinfo=UTC)
        )
        for resource_id, hours_per_day in booked_hours.items():
            for day, hours in hours_per_day.items():
                remaining_hours_per_day[resource_id][day] -= hours
                remaining_hours_per_week[resource_id][
                    self.env["resource.resource"].browse(resource_id)._get_week_of(day)
                ] -= hours

        def find_resource(shift):
            shift_intervals = Intervals(
                [
                    (
                        shift.start_datetime.astimezone(user_tz),
                        shift.end_datetime.astimezone(user_tz),
                        PlanningShift,
                    )
                ]
            )
            for resources_dict in resources_dicts:
                resource_ids = shift._get_resource_ids_for_assignment(resources_dict)
                for resource in self.env["resource.resource"].browse(resource_ids):
                    split_shift_intervals = (
                        shift_intervals
                        & schedule_intervals_per_resource_id[resource.id]
                    )
                    if not split_shift_intervals:
                        continue
                    is_flex_resource = resource._is_flexible()
                    if is_flex_resource:
                        work_hours_per_day = defaultdict(float)
                        working_hours = resource._get_flexible_resource_work_hours(
                            split_shift_intervals,
                            flexible_resources_hours_per_day[resource.id],
                            flexible_resources_hours_per_week[resource.id],
                            work_hours_per_day,
                        )
                        rate = (
                            shift.allocated_hours / working_hours
                            if working_hours > 0.0
                            else float("inf")
                        )

                        is_overloaded = False
                        hours_to_work_per_week = defaultdict(float)
                        for day, hours in work_hours_per_day.items():
                            week = resource._get_week_of(day)
                            hours_to_work = hours * rate
                            hours_to_work_per_week[week] += hours_to_work
                            if (
                                hours_to_work
                                > remaining_hours_per_day[resource.id].get(day, 0.0)
                                + 1e-7
                                or hours_to_work_per_week[week]
                                > remaining_hours_per_week[resource.id].get(week, 0.0)
                                + 1e-7
                            ):
                                is_overloaded = True
                                break

                        if is_overloaded:
                            continue
                    else:
                        rate = (
                            shift.allocated_hours
                            * 3600
                            / sum(
                                round((end - start).total_seconds())
                                for start, end, rec in split_shift_intervals
                            )
                        )
                    percentage = 100 * rate
                    bookings = loads.setdefault(resource.id, [])
                    if (
                        peak_capacity(
                            bookings, shift.start_datetime, shift.end_datetime
                        )
                        + percentage
                        <= resource.booking_limit_percentage + 1e-7
                    ):
                        shift.write(
                            {
                                "resource_id": resource.id,
                                "allocated_percentage": percentage,
                                "allocated_hours": shift.allocated_hours,
                            }
                        )
                        bookings.append(
                            (shift.start_datetime, shift.end_datetime, percentage)
                        )
                        if is_flex_resource:
                            for day, hours in work_hours_per_day.items():
                                remaining_hours_per_day[resource.id][day] -= (
                                    hours * rate
                                )
                                remaining_hours_per_week[resource.id][
                                    resource._get_week_of(day)
                                ] -= hours * rate
                        return True
            return False

        return {"open_shift_assigned": open_shifts.filtered(find_resource).ids}

    @api.model
    def action_rollback_auto_plan_ids(self, shifts_data) -> None:
        open_shift_assigned = shifts_data["open_shift_assigned"]
        self.browse(open_shift_assigned).resource_id = False


    @api.model
    def get_gantt_data(
        self,
        domain,
        groupby,
        read_specification,
        limit=None,
        offset=0,
        unavailability_fields=None,
        progress_bar_fields=None,
        start_date=None,
        stop_date=None,
        scale=None,
    ):
        result = super(PlanningSlot, self.with_context(scale=scale)).get_gantt_data(
            domain,
            groupby,
            read_specification,
            limit=limit,
            offset=offset,
            unavailability_fields=unavailability_fields,
            progress_bar_fields=progress_bar_fields,
            start_date=start_date,
            stop_date=stop_date,
            scale=scale,
        )
        if "resource_id" in groupby:
            result["working_periods"] = self._gantt_resource_employees_working_periods(
                result["groups"], start_date, stop_date
            )
        return result

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        if field_name != "resource_id":
            return super()._gantt_unavailability(
                field_name, res_ids, start, stop, scale
            )

        resources = self.env["resource.resource"].browse(res_ids)
        leaves_mapping = resources._get_unavailable_intervals(start, stop)
        company_leaves = self.env.company.resource_calendar_id._unavailable_intervals(
            start.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
        )
        cell_dt = (
            timedelta(hours=1) if scale in ["day", "week"] else timedelta(hours=12)
        )

        result = {False: []}
        for resource in resources:
            if (resource.id not in res_ids) or (
                resource and resource._is_fully_flexible()
            ):
                continue
            calendar = leaves_mapping.get(resource.id, company_leaves)
            notable_intervals = filter(
                lambda interval: interval[1] - interval[0] >= cell_dt, calendar
            )
            result[resource.id] = [
                {"start": interval[0], "stop": interval[1]}
                for interval in notable_intervals
            ]

        return result

    @api.model
    def get_unusual_days(self, date_from, date_to=None):
        return self.env.user.employee_id._get_unusual_days(date_from, date_to)

    @api.model
    def _cron_clear_past_request_to_switch(self) -> None:
        self.search([("request_to_switch", "=", True)]).filtered(
            "is_past"
        ).request_to_switch = False


    @api.model
    def action_copy_previous_week(
        self, date_start_week, view_domain
    ) -> list | Literal[False]:
        date_end_copy = datetime.strptime(
            date_start_week, DEFAULT_SERVER_DATETIME_FORMAT
        )
        date_start_copy = date_end_copy - relativedelta(days=7)
        domain = [("recurrency_id", "=", False), ("was_copied", "=", False)]
        for dom in view_domain:
            if dom in ["|", "&", "!"]:
                domain.append(dom)
            elif dom[0] == "start_datetime":
                domain.append(("start_datetime", ">=", date_start_copy))
            elif dom[0] == "end_datetime":
                domain.append(("end_datetime", "<=", date_end_copy))
            else:
                domain.append(tuple(dom))
        slots_to_copy = self.search(domain)

        new_slot_values = []
        new_slot_values = slots_to_copy._copy_slots(
            date_start_copy, date_end_copy, relativedelta(days=7)
        )
        slots_to_copy.write({"was_copied": True})
        if new_slot_values:
            return [self.create(new_slot_values).ids, slots_to_copy.ids]
        return False

    def action_rollback_copy_previous_week(self, copied_slot_ids) -> None:
        self.browse(copied_slot_ids).was_copied = False
        self.exists().unlink()


    def get_people_without_email(self) -> dict | None:
        self.check_singleton()
        resources = self.resource_id or self._get_resources_to_send_slot()
        without_email = resources.filtered(
            lambda resource: not resource._get_planning_email()
        )
        if not without_email or not without_email.has_access("write"):
            return None
        context = dict(self.env.context)
        context["force_email"] = True
        context["form_view_ref"] = "planning.resource_resource_view_form_email"
        return {
            "relation": "resource.resource",
            "res_ids": without_email.ids,
            "context": context,
        }

    def _get_resources_to_send_slot(self):
        self.check_singleton()
        if self.resource_id and self.resource_id._get_planning_email():
            return self.resource_id
        domain = (
            Domain("company_id", "=", self.company_id.id)
            & Domain("type", "=", "human")
            & Domain("partner_id.email", "!=", False)
        )
        if self.role_id:
            domain &= Domain("role_ids", "=", False) | Domain(
                "role_ids", "in", self.role_id.id
            )
        return self.env["resource.resource"].sudo().search(domain)

    def _get_notification_action(self, notif_type, message) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": notif_type,
                "message": message,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_planning_publish_and_send(self):
        notif_type = "success"
        if not self or all(shift.state != "1_draft" for shift in self):
            start = end = False
        else:
            start, end = (
                min(self.mapped("start_datetime")),
                max(self.mapped("end_datetime")),
            )
        if not start or not end:
            notif_type = "warning"
            message = self.env._("There are no shifts to publish and send.")
        else:
            planning = self.env["planning.planning"].create(
                {
                    "start_datetime": start,
                    "end_datetime": end,
                }
            )
            planning._send_planning(slots=self, resources=self.resource_id)
            message = self.env._(
                "The shifts have successfully been published and sent."
            )
        return self._get_notification_action(notif_type, message)

    def action_send(self):
        self.check_singleton()
        if self.state == "1_draft" and (
            not self.resource_id or not self.resource_id._get_planning_email()
        ):
            self.state = "2_published"
        resources = self._get_resources_to_send_slot()
        self._send_slot(resources, self.start_datetime, self.end_datetime)
        message = self.env._("Shift sent")
        return self._get_notification_action("success", message)

    def action_save_template(self) -> None:
        self.check_singleton()
        if self.allow_template_creation:
            self.template_creation = True

    def action_unpublish(self):
        if not self.env.user.has_group("planning.group_planning_manager"):
            raise AccessError(
                self.env._("You are not allowed to reset shifts to draft.")
            )
        published_shifts = self.filtered(
            lambda shift: (
                shift.state == "2_published" and shift.resource_type == "human"
            )
        )
        if published_shifts:
            published_shifts.write({"state": "1_draft", "publication_warning": False})
            notif_type = "success"
            message = self.env._("Shifts reset to draft")
        else:
            notif_type = "warning"
            message = self.env._("There are no shifts to reset to draft.")
        return self._get_notification_action(notif_type, message)

    def _print_planning_get_fields_to_copy(self):
        return [
            "employee_id",
            "company_id",
            "allocated_percentage",
            "allocated_hours",
            "resource_id",
            "start_datetime",
            "end_datetime",
            "role_id",
        ]

    def _print_planning_get_slot_title(self, slot_start, slot_end, tz_info, group_by):
        def print_planning_format_time(date, tz_info):
            return format_time(self.env, date.time(), tz_info, "HH:mm")

        allocated_hours_formatted = ""
        if self.allocated_percentage != 100:
            (unitary_part, decimal_part) = float_split_str(
                self.allocated_hours,
                precision_digits=2,
            )
            allocated_hours_formatted = (
                f" ({unitary_part}h{decimal_part if decimal_part != '00' else ''})"
            )
        name_get = ""
        if group_by == "role_id":
            if self.resource_id:
                name_get = f" {self.resource_id.name}"
        elif group_by == "resource_id":
            if self.role_id:
                name_get = f" {self.role_id.name}"
        else:
            name_get = f" {self.resource_id.name}" if self.resource_id else ""
            if self.role_id:
                if name_get:
                    name_get += f" - {self.role_id.name}"
                else:
                    name_get = f" {self.role_id.name}"

        return f"{print_planning_format_time(slot_start, tz_info)} – {print_planning_format_time(slot_end, tz_info)}{allocated_hours_formatted}{name_get}"

    @api.model
    def action_print_plannings(self, date_start, date_end, group_bys, domain):

        def print_planning_split_fake_pill(shift, values):
            shift.check_singleton()
            assert (
                "start_datetime" in values
                and "end_datetime" in values
                and not shift._origin
            )
            record = print_planning_create_fake_pill(
                shift,
                {
                    "start_datetime": values.get("start_datetime")
                    .astimezone(UTC)
                    .replace(tzinfo=None)
                },
            )
            shift.update(
                {
                    "end_datetime": values.get("end_datetime")
                    .astimezone(UTC)
                    .replace(tzinfo=None)
                }
            )
            return record

        def print_planning_create_fake_pill(shift, vals=None):
            record = (
                self.env["planning.slot"]
                .with_context(planning_print_pill=True)
                .new(
                    {
                        **shift._read_format(
                            shift._print_planning_get_fields_to_copy()
                        )[0],
                        **(vals or {}),
                    }
                )
            )
            source_of[record] = source_of.get(shift, shift)
            record._compute_allocated_hours()
            return record

        def print_planning_get_fake_pill_datetime(
            datetime_per_resource_per_day, resource_id, day, tz_info, default
        ):
            if day in datetime_per_resource_per_day[resource_id]:
                return datetime_per_resource_per_day[resource_id][day].astimezone(
                    tz_info
                )

            return datetime.combine(day, default).replace(tzinfo=tz_info)

        def print_planning_get_fake_pill_start_datetime(
            start_datetime_per_resource_per_day, resource_id, day, tz_info
        ):
            return print_planning_get_fake_pill_datetime(
                start_datetime_per_resource_per_day, resource_id, day, tz_info, time.min
            )

        def print_planning_get_fake_pill_end_datetime(
            end_datetime_per_resource_per_day, resource_id, day, tz_info
        ):
            return print_planning_get_fake_pill_datetime(
                end_datetime_per_resource_per_day, resource_id, day, tz_info, time.max
            )

        def print_planning_add_slot(
            shift, tz_info, group_by_slots_per_day_per_week, group, weeks, group_by
        ):
            if (days := days_by_slot.get(source_of.get(shift))) is not None:
                shift_tz = timezone(shift.resource_id.tz)
                first = shift.start_datetime.replace(tzinfo=UTC).astimezone(shift_tz)
                last = last_day_of(
                    first, shift.end_datetime.replace(tzinfo=UTC).astimezone(shift_tz)
                )
                shift.allocated_hours = round(
                    sum(
                        hours
                        for day, hours in days.items()
                        if first.date() <= day <= last
                    ),
                    2,
                )
            if float_is_zero(shift.allocated_hours, precision_digits=2):
                return

            slot_start = shift.start_datetime.astimezone(tz_info)
            slot_end = shift.end_datetime.astimezone(tz_info)
            date = format_date(self.env, slot_start)
            for index, week, _dummy in weeks:
                if date in week:
                    group_by_slots_per_day_per_week[index][group][date].append(
                        {
                            "title": shift._print_planning_get_slot_title(
                                slot_start, slot_end, tz_info, group_by
                            ),
                            "style": f"background-color: {shift.role_id._get_light_color(0.5, not shift.resource_id)};",
                        }
                    )
                    return

        def print_planning_update_datetime(
            _datetime, resource_id, datetime_per_resource_per_day, func
        ):
            day = _datetime.date()
            if day in datetime_per_resource_per_day[resource_id]:
                datetime_per_resource_per_day[resource_id][day] = func(
                    datetime_per_resource_per_day[resource_id][day], _datetime
                )
            else:
                datetime_per_resource_per_day[resource_id][day] = _datetime

        def print_planning_flexible_resources_work_intervals(start, end, resources):
            assert all(
                resource._is_flexible() and not resource._is_fully_flexible()
                for resource in resources
            )
            return {
                resource.id: Intervals(
                    [(start, end, self.env["resource.calendar.attendance"])]
                )
                for resource in resources
            }

        group_bys = [
            g
            for g in (group_bys or [])
            if self._fields[g.split(":")[0]].type not in {"datetime", "date"}
        ]
        if not group_bys:
            group_bys = ["resource_id"]

        group_by = group_bys[-1]
        date_start = datetime.strptime(date_start, DEFAULT_SERVER_DATETIME_FORMAT)
        date_end = datetime.strptime(date_end, DEFAULT_SERVER_DATETIME_FORMAT)

        if date_end < date_start:
            date_start, date_end = date_end, date_start

        group_by_slots = self.env["planning.slot"]._read_group(
            domain,
            [group_by],
            ["id:recordset"],
        )

        if not group_by_slots:
            return False

        tz_info = timezone(self._get_tz())
        day_start_in_user_tz = date_start.astimezone(tz_info).date()
        day_end_in_user_tz = last_day_of(
            date_start.astimezone(tz_info), date_end.astimezone(tz_info)
        )
        days_count = (day_end_in_user_tz - day_start_in_user_tz).days + 1
        days = [day_start_in_user_tz + timedelta(days=i) for i in range(days_count)]
        group_by_slots_per_day_per_week = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        unassigned = (
            self.env._("Open Shifts")
            if group_by == "resource_id"
            else self.env._(
                "Undefined %(group)s",
                group=self.fields_get([group_by])[group_by]["string"],
            )
        )
        group_by_name_by_id = {}
        non_flexible_resources_ids = set()
        flexible_resources_ids = set()

        for g, slots in group_by_slots:
            group_by_name_by_id[g.id if g else False] = (
                g.display_name if g else unassigned
            )
            for slot in slots:
                if slot.resource_id:
                    (
                        flexible_resources_ids
                        if not slot.resource_id._is_fully_flexible()
                        and slot.resource_id._is_flexible()
                        else non_flexible_resources_ids
                    ).add(slot.resource_id.id)

        non_flexible_resources = self.env["resource.resource"].browse(
            non_flexible_resources_ids
        )
        source_of = {}
        days_by_slot = (
            self.env["planning.slot"]
            .union(*(slots for _group, slots in group_by_slots))
            ._filter_first_served()
            ._get_first_served_days()
        )
        flexible_resources = self.env["resource.resource"].browse(
            flexible_resources_ids
        )

        start_utc, end_utc = (
            date_start.replace(tzinfo=UTC),
            date_end.replace(tzinfo=UTC),
        )
        resources_work_intervals, _dummy = (
            non_flexible_resources._get_valid_work_intervals(start_utc, end_utc)
        )

        resources_work_intervals.update(
            print_planning_flexible_resources_work_intervals(
                start_utc, end_utc, flexible_resources
            )
        )

        weeks = [
            (
                int(i / 7),
                [format_date(self.env, day) for day in days[i : i + 7]],
                self.env._(
                    "Week from %(start_date)s to %(end_date)s",
                    start_date=format_date(self.env, days[i : i + 7][0]),
                    end_date=format_date(self.env, days[i : i + 7][-1]),
                ),
            )
            for i in range(0, len(days), 7)
        ]

        start_datetime_per_resource_per_day, end_datetime_per_resource_per_day = (
            defaultdict(dict),
            defaultdict(dict),
        )
        for resource_id, intervals in resources_work_intervals.items():
            for start_datetime, end_datetime, _dummy in intervals._items:
                print_planning_update_datetime(
                    start_datetime,
                    resource_id,
                    start_datetime_per_resource_per_day,
                    min,
                )
                print_planning_update_datetime(
                    end_datetime, resource_id, end_datetime_per_resource_per_day, max
                )

        for group_id, slots in sorted(
            group_by_slots, key=lambda x: x[0].display_name if x[0] else ""
        ):
            group = group_id.id if group_id else False
            for slot in slots:
                resource_id = slot.resource_id
                slot_start = slot.start_datetime.astimezone(tz_info)
                slot_end = slot.end_datetime.astimezone(tz_info)

                slot_start_day = slot_start.date()
                slot_end_day = last_day_of(slot_start, slot_end)

                if slot_start_day == slot_end_day:
                    print_planning_add_slot(
                        slot,
                        tz_info,
                        group_by_slots_per_day_per_week,
                        group,
                        weeks,
                        group_by,
                    )
                else:
                    fake_slot = print_planning_create_fake_pill(slot)

                    first_day = days[0]
                    if slot_start_day < first_day:
                        fake_slot = print_planning_split_fake_pill(
                            fake_slot,
                            {
                                "start_datetime": print_planning_get_fake_pill_start_datetime(
                                    start_datetime_per_resource_per_day,
                                    resource_id.id,
                                    first_day,
                                    tz_info,
                                ),
                                "end_datetime": print_planning_get_fake_pill_end_datetime(
                                    end_datetime_per_resource_per_day,
                                    resource_id.id,
                                    first_day + timedelta(days=-1),
                                    tz_info,
                                ),
                            },
                        )

                    last_day = days[-1]
                    if slot_end_day > last_day:
                        print_planning_split_fake_pill(
                            fake_slot,
                            {
                                "start_datetime": print_planning_get_fake_pill_start_datetime(
                                    start_datetime_per_resource_per_day,
                                    resource_id.id,
                                    last_day + timedelta(days=1),
                                    tz_info,
                                ),
                                "end_datetime": print_planning_get_fake_pill_end_datetime(
                                    end_datetime_per_resource_per_day,
                                    resource_id.id,
                                    last_day,
                                    tz_info,
                                ),
                            },
                        )

                    current_day = fake_slot.start_datetime.date()
                    last_day = fake_slot.end_datetime.date()
                    while current_day < last_day:
                        split_slot = print_planning_split_fake_pill(
                            fake_slot,
                            {
                                "start_datetime": print_planning_get_fake_pill_start_datetime(
                                    start_datetime_per_resource_per_day,
                                    resource_id.id,
                                    current_day + timedelta(days=1),
                                    tz_info,
                                ),
                                "end_datetime": print_planning_get_fake_pill_end_datetime(
                                    end_datetime_per_resource_per_day,
                                    resource_id.id,
                                    current_day,
                                    tz_info,
                                ),
                            },
                        )

                        print_planning_add_slot(
                            fake_slot,
                            tz_info,
                            group_by_slots_per_day_per_week,
                            group,
                            weeks,
                            group_by,
                        )
                        fake_slot = split_slot
                        current_day += timedelta(days=1)

                    print_planning_add_slot(
                        fake_slot,
                        tz_info,
                        group_by_slots_per_day_per_week,
                        group,
                        weeks,
                        group_by,
                    )

        group_by_slots_per_day_per_week_formatted = {
            week: [(group, val) for group, val in data.items()]
            for week, data in group_by_slots_per_day_per_week.items()
        }

        return (
            self.env.ref("planning.report_planning_slot")
            .with_context(discard_logo_check=True)
            .report_action(
                None,
                data={
                    "group_by_slots_per_day_per_week": group_by_slots_per_day_per_week_formatted,
                    "weeks": weeks,
                    "group_by_name_by_id": group_by_name_by_id,
                },
            )
        )


    def _get_slot_duration_capped(self):
        self.check_singleton()
        slot_duration = self._get_slot_duration() or 0.0
        if not slot_duration:
            return 0.0

        period = self.end_datetime - self.start_datetime
        if self.employee_id:
            max_hours_per_day = self.employee_id.resource_calendar_id.hours_per_day
        else:
            max_hours_per_day = self.company_id.resource_calendar_id.hours_per_day
        max_duration = (period.days + (1 if period.seconds else 0)) * max_hours_per_day
        if not max_duration or max_duration >= slot_duration:
            return slot_duration
        return max_duration


    def _add_delta_with_dst(self, start, delta):
        tz = self._get_tzinfo()
        start = start.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)
        result = start + delta
        return wall_to_utc(result, tz)

    def _init_remaining_hours_to_plan(self, remaining_hours_to_plan):
        self.check_singleton()
        return True

    def _update_remaining_hours_to_plan_and_values(
        self, remaining_hours_to_plan, values
    ):
        self.check_singleton()
        return True

    def _prepare_split_slot_vals_list(
        self, values, intervals, remaining_hours_to_plan, unassign=False
    ) -> list[ValuesType]:
        self.check_singleton()
        split_slot_values = []
        for start_inter, end_inter, _resource in intervals:
            new_slot_vals = {
                **values,
                "start_datetime": start_inter.astimezone(UTC).replace(tzinfo=None),
                "end_datetime": end_inter.astimezone(UTC).replace(tzinfo=None),
            }
            was_updated = self._update_remaining_hours_to_plan_and_values(
                remaining_hours_to_plan, new_slot_vals
            )
            period = end_inter - start_inter
            slot_duration = period.total_seconds() / 3600
            if (
                not unassign
                and self.resource_id._is_flexible()
                and not self.resource_id._is_fully_flexible()
            ):
                max_hours_per_day = self.employee_id.resource_calendar_id.hours_per_day
                max_duration = (
                    period.days + (1 if period.seconds else 0)
                ) * max_hours_per_day
                slot_duration = min(slot_duration, max_duration)
            new_slot_vals["allocated_hours"] = float_round(
                slot_duration * (self.allocated_percentage / 100.0), precision_digits=2
            )
            if not was_updated:
                return split_slot_values
            if unassign:
                new_slot_vals["resource_id"] = False
            split_slot_values.append(new_slot_vals)
        return split_slot_values

    def _copy_slots(self, start_dt, end_dt, delta):
        resource_per_calendar = defaultdict(lambda: self.env["resource.resource"])
        resource_calendar_validity_intervals = defaultdict(dict)
        attendance_intervals_per_resource = defaultdict(
            Intervals
        )
        unavailable_intervals_per_resource = defaultdict(
            Intervals
        )
        attendance_intervals_per_calendar = defaultdict(
            Intervals
        )
        leave_intervals_per_calendar = defaultdict(
            Intervals
        )
        new_slot_values = []
        start_dt_delta = start_dt + delta
        end_dt_delta = end_dt + delta
        start_dt_delta_utc = start_dt_delta.replace(tzinfo=UTC)
        end_dt_delta_utc = end_dt_delta.replace(tzinfo=UTC)
        resource_slots = self.search(
            [
                ("start_datetime", ">=", start_dt_delta),
                ("end_datetime", "<=", end_dt_delta),
                ("resource_id", "in", self.resource_id.ids),
            ]
        )
        for slot in resource_slots:
            unavailable_intervals_per_resource[slot.resource_id] |= Intervals(
                [
                    (
                        slot.start_datetime.replace(tzinfo=UTC),
                        slot.end_datetime.replace(tzinfo=UTC),
                        self.env["resource.schedule.exception"],
                    )
                ]
            )
        resource_calendar_validity_intervals = (
            self.resource_id.sudo()
            .filtered(lambda resource: not resource._is_flexible())
            ._get_calendars_validity_within_period(start_dt_delta_utc, end_dt_delta_utc)
        )
        for slot in self:
            if slot.resource_id:
                for calendar in resource_calendar_validity_intervals[
                    slot.resource_id.id
                ]:
                    resource_per_calendar[calendar] |= slot.resource_id
            company_calendar_id = slot.company_id.resource_calendar_id
            resource_per_calendar[company_calendar_id] |= self.env[
                "resource.resource"
            ]
        for calendar, resources in resource_per_calendar.items():
            if not calendar:
                continue
            attendances = {
                resource_id: Intervals(work_interval._items)
                for resource_id, work_interval in calendar._attendance_intervals_batch(
                    start_dt_delta_utc, end_dt_delta_utc, resources=resources
                ).items()
            }
            leaves = calendar._leave_intervals_batch(
                start_dt_delta_utc, end_dt_delta_utc, resources=resources
            )
            attendance_intervals_per_calendar[calendar] = attendances[False]
            leave_intervals_per_calendar[calendar] = leaves[False]
            for resource in resources:
                attendance_intervals_per_resource[resource] |= (
                    attendances[resource.id]
                    & resource_calendar_validity_intervals[resource.id][calendar]
                )
                unavailable_intervals_per_resource[resource] |= (
                    leaves[resource.id]
                    & resource_calendar_validity_intervals[resource.id][calendar]
                )
        remaining_hours_to_plan = {}
        for slot in self:
            if not slot._init_remaining_hours_to_plan(remaining_hours_to_plan):
                continue
            values = slot.copy_data(default={"state": "1_draft"})[0]
            if not values.get("start_datetime") or not values.get("end_datetime"):
                continue
            values["start_datetime"] = slot._add_delta_with_dst(
                values["start_datetime"], delta
            )
            values["end_datetime"] = slot._add_delta_with_dst(
                values["end_datetime"], delta
            )
            if slot.allocation_type == "forecast" and (
                not slot.resource_id or slot.resource_id._is_fully_flexible()
            ):
                new_slot_values.append(values)
                continue
            if any(
                new_slot["resource_id"] == values["resource_id"]
                and new_slot["start_datetime"] <= values["end_datetime"]
                and new_slot["end_datetime"] >= values["start_datetime"]
                for new_slot in new_slot_values
            ):
                values["resource_id"] = False
            interval = Intervals(
                [
                    (
                        values.get("start_datetime").replace(tzinfo=UTC),
                        values.get("end_datetime").replace(tzinfo=UTC),
                        self.env["resource.calendar.attendance"],
                    )
                ]
            )
            company_calendar = slot.company_id.resource_calendar_id
            if slot.resource_id and slot.resource_id._is_flexible():
                attendance_interval_resource = interval
                attendance_interval_company = interval
            else:
                attendance_resource = (
                    attendance_intervals_per_resource[slot.resource_id]
                    if slot.resource_id
                    else attendance_intervals_per_calendar[company_calendar]
                )
                attendance_interval_resource = interval & attendance_resource
                attendance_interval_company = (
                    interval & attendance_intervals_per_calendar[company_calendar]
                )
            unavailable_interval_company = (
                interval & leave_intervals_per_calendar[company_calendar]
            )
            unavailable_interval_resource = (
                unavailable_interval_company
                if not slot.resource_id
                else (interval & unavailable_intervals_per_resource[slot.resource_id])
            )
            if not unavailable_interval_company:

                if slot.allocation_type == "planning":
                    if (
                        unavailable_interval_resource
                        or not attendance_interval_resource
                    ):
                        if slot.resource_type != "human":
                            continue
                        values["resource_id"] = False
                    if not slot._update_remaining_hours_to_plan_and_values(
                        remaining_hours_to_plan, values
                    ):
                        continue
                    new_slot_values.append(values)
                else:
                    if attendance_interval_resource:
                        work_interval_employee = (
                            attendance_interval_resource - unavailable_interval_resource
                        )
                        unassigned_interval = (
                            unavailable_interval_resource - unavailable_interval_company
                        ) & (attendance_interval_company - unavailable_interval_company)
                        split_slot_values = slot._prepare_split_slot_vals_list(
                            values, work_interval_employee, remaining_hours_to_plan
                        )
                        if slot.resource_type == "human":
                            split_slot_values += slot._prepare_split_slot_vals_list(
                                values,
                                unassigned_interval,
                                remaining_hours_to_plan,
                                unassign=True,
                            )
                    elif slot.resource_type != "human":
                        continue
                    else:
                        unassigned_interval = (
                            attendance_interval_company - unavailable_interval_company
                        )
                        split_slot_values = slot._prepare_split_slot_vals_list(
                            values,
                            unassigned_interval,
                            remaining_hours_to_plan,
                            unassign=True,
                        )
                    new_slot_values += self._merge_slots_values(
                        split_slot_values, unassigned_interval
                    )
        return new_slot_values

    def _display_name_fields(self):
        return ["resource_id", "role_id"]

    def _get_fields_breaking_publication(self):
        return [
            "resource_id",
            "resource_type",
            "start_datetime",
            "end_datetime",
            "role_id",
        ]

    @api.model
    def _get_fields_template(self) -> dict:
        return {
            "role_id": "role_id",
            "start_time": "start_datetime",
            "end_time": "end_datetime",
            "duration_days": "working_days_count",
        }

    def _get_tzinfo(self):
        try:
            return timezone(self._get_tz())
        except ZoneInfoNotFoundError:
            return UTC

    def _get_tz(self):
        return (
            self.env.user.tz
            or self.employee_id.tz
            or self.resource_id.tz
            or self.env.context.get("tz")
            or self.company_id.resource_calendar_id.tz
            or "UTC"
        )

    def _prepare_template_values(self) -> dict:
        destination_tz = timezone(self._get_tz())
        start_datetime = self.start_datetime.replace(tzinfo=UTC).astimezone(
            destination_tz
        )
        end_datetime = self.end_datetime.replace(tzinfo=UTC).astimezone(destination_tz)

        duration_days = days_span(start_datetime, end_datetime)

        return {
            "start_time": start_datetime.hour + start_datetime.minute / 60.0,
            "end_time": end_datetime.hour + end_datetime.minute / 60.0,
            "duration_days": duration_days,
            "role_id": self.role_id.id,
        }

    def _manage_archived_resources(self, departure_date) -> None:
        shift_vals_list = []
        shift_ids_to_remove_resource = []
        for slot in self:
            split_time = (
                departure_date.replace(tzinfo=timezone(self._get_tz()))
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            if (slot.start_datetime < split_time) and (slot.end_datetime > split_time):
                shift_vals_list.append(
                    {
                        "start_datetime": split_time,
                        **slot._prepare_shift_vals(),
                    }
                )
                if split_time > slot.start_datetime:
                    slot.write({"end_datetime": split_time})
            elif slot.start_datetime >= split_time:
                shift_ids_to_remove_resource.append(slot.id)
        if shift_vals_list:
            self.sudo().create(shift_vals_list)
        if shift_ids_to_remove_resource:
            self.sudo().browse(shift_ids_to_remove_resource).write(
                {"resource_id": False}
            )

    def _group_expand_resource_id(self, resources, domain):
        dom_tuples = [
            (dom[0], dom[1])
            for dom in domain
            if isinstance(dom, (tuple, list)) and len(dom) == 3
        ]
        resource_ids = self.env.context.get("filter_resource_ids", False)
        if resource_ids:
            return self.env["resource.resource"].search([("id", "in", resource_ids)])
        if (
            self.env.context.get("planning_expand_resource")
            and ("start_datetime", "<") in dom_tuples
            and ("end_datetime", ">") in dom_tuples
        ):
            search_on_role_domain = Domain.TRUE
            search_on_ressource_domain = Domain.TRUE
            search_on_department_domain = Domain.TRUE
            if (
                ("role_id", "=") in dom_tuples
                or ("role_id", "ilike") in dom_tuples
                or ("role_id", "in") in dom_tuples
            ):
                role_search_domain = Domain(
                    self._expand_domain_m2o_groupby(domain, "role_id")
                )
                role_ids = self.env["resource.role"].search(role_search_domain).ids
                search_on_role_domain = Domain("role_ids", "in", role_ids)
            if (
                ("resource_id", "=") in dom_tuples
                or ("resource_id", "ilike") in dom_tuples
                or ("resource_id", "in") in dom_tuples
            ):
                search_on_ressource_domain = Domain(
                    self._expand_domain_m2o_groupby(domain, "resource_id")
                )
            if (
                ("department_id", "=") in dom_tuples
                or ("department_id", "ilike") in dom_tuples
                or ("department_id", "in") in dom_tuples
            ):
                department_search_domain = Domain(
                    self._expand_domain_m2o_groupby(domain, "department_id")
                )
                department_ids = (
                    self.env["hr.department"].search(department_search_domain).ids
                )
                search_on_department_domain = Domain(
                    "employee_id.department_id", "in", department_ids
                )
                if search_on_ressource_domain == Domain("id", "=", False):
                    search_on_ressource_domain = Domain.TRUE
            filters = self._expand_domain_dates(domain)
            resources = self.env["planning.slot"].search(filters).mapped("resource_id")
            search_on_expanded_dates = Domain("id", "in", resources.ids)
            if (
                search_on_role_domain
                or search_on_department_domain
                or search_on_ressource_domain
            ):
                search_domain = Domain.AND(
                    [
                        search_on_role_domain,
                        search_on_department_domain,
                        search_on_ressource_domain,
                    ]
                )
                return self.env["resource.resource"].search(
                    search_domain | search_on_expanded_dates
                )
            return self.env["resource.resource"].search(search_on_expanded_dates)
        return resources

    def _read_group_role_id(self, roles, domain):
        dom_tuples = [
            (dom[0], dom[1])
            for dom in domain
            if isinstance(dom, list) and len(dom) == 3
        ]
        if (
            self.env.context.get("planning_expand_role")
            and ("start_datetime", "<") in dom_tuples
            and ("end_datetime", ">") in dom_tuples
        ):
            if ("role_id", "=") in dom_tuples or ("role_id", "ilike") in dom_tuples:
                filter_domain = self._expand_domain_m2o_groupby(domain, "role_id")
                return self.env["resource.role"].search(filter_domain)
            filters = Domain.AND(
                [[("role_id.active", "=", True)], self._expand_domain_dates(domain)]
            )
            return self.env["planning.slot"].search(filters).mapped("role_id")
        return roles

    @api.model
    def _expand_domain_m2o_groupby(self, domain, filter_field=False):
        filter_domains = []
        for dom in domain:
            if dom[0] == filter_field:
                field = self._fields[dom[0]]
                if field.type == "many2one" and len(dom) == 3:
                    if dom[1] in ["=", "in"]:
                        filter_domains.append([("id", dom[1], dom[2])])
                    elif dom[1] == "ilike":
                        rec_name = self.env[field.comodel_name]._rec_name
                        filter_domains.append([(rec_name, dom[1], dom[2])])
        return Domain.OR(filter_domains) if filter_domains else Domain.TRUE

    def _expand_domain_dates(self, domain):
        delta = get_timedelta(1, self.env.context.get("scale", "week"))

        def update_start_end_dates(cond):
            if cond.field_expr == "start_datetime" and cond.operator[0] == "<":
                value = cond.value or datetime.now()
                value += delta
            elif cond.field_expr == "end_datetime" and cond.operator[0] == ">":
                value = cond.value or datetime.now()
                value -= delta
            else:
                return cond
            return Domain(cond.field_expr, cond.operator, value)

        return Domain(domain).optimize_full(self).map_conditions(update_start_end_dates)

    @api.model
    def _format_datetime_to_user_tz(
        self, datetime_without_tz, record_env, tz=None, lang_code=False
    ):
        return format_datetime(
            record_env,
            datetime_without_tz,
            tz=tz,
            dt_format="short",
            lang_code=lang_code,
        )

    def _send_slot(
        self,
        resources,
        start_datetime,
        end_datetime,
        include_unassigned=True,
        message=None,
    ) -> None:
        if not include_unassigned:
            self = self.filtered(lambda s: s.resource_id)
        if not self:
            return
        self.check_singleton()

        with_backend = resources.sudo().filtered(
            lambda resource: resource.user_id and not resource.user_id._is_portal()
        )
        without_backend = resources - with_backend
        planning = False
        resource_url_map = {}
        if without_backend:
            planning = self.env["planning.planning"].create(
                {
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "include_unassigned": include_unassigned,
                }
            )
            resource_url_map = without_backend.sudo()._planning_get_url(
                planning.date_start, planning.date_end, planning
            )

        template = self.env.ref("planning.email_template_slot_single")
        resource_url_map.update(
            with_backend._planning_get_url(start_datetime.date(), end_datetime.date())
        )

        cal_url = self._get_slot_resource_urls()
        view_context = dict(self.env.context)
        view_context.update(
            {
                "open_shift_available": not self.resource_id,
                "mail_subject": self.env._("Planning: new open shift available on"),
                "google_url": cal_url["google_url"],
            }
        )

        if self.resource_id:
            resources = self.resource_id
            if self.allow_self_unassign and not self.is_unassign_deadline_passed:
                if resources.sudo().filtered("user_id"):
                    unavailable_link = "/planning/unassign/%s/%s" % (
                        self.resource_id.sudo().planning_token,
                        self.id,
                    )
                else:
                    unavailable_link = "/planning/%s/%s/unassign/%s?message=1" % (
                        planning._page_token(self.resource_id),
                        self.resource_id.sudo().planning_token,
                        self.id,
                    )
                view_context.update({"unavailable_link": unavailable_link})
            view_context.update({"mail_subject": self.env._("Planning: new shift on")})

        mails_to_send_ids = []
        for resource in resources.sudo().filtered(
            lambda resource: resource._get_planning_email()
        ):
            if not self.resource_id and resource in with_backend and not self.is_past:
                view_context.update(
                    {
                        "available_link": "/planning/assign/%s/%s"
                        % (resource.planning_token, self.id)
                    }
                )
            elif not self.resource_id and not self.is_past:
                view_context.update(
                    {
                        "available_link": "/planning/%s/%s/assign/%s?message=1"
                        % (
                            planning._page_token(resource),
                            resource.planning_token,
                            self.id,
                        )
                    }
                )
            start_datetime = self._format_datetime_to_user_tz(
                self.start_datetime,
                resource.env,
                tz=resource.tz,
                lang_code=resource.partner_id.lang,
            )
            end_datetime = self._format_datetime_to_user_tz(
                self.end_datetime,
                resource.env,
                tz=resource.tz,
                lang_code=resource.partner_id.lang,
            )
            unassign_deadline = self._format_datetime_to_user_tz(
                self.unassign_deadline,
                resource.env,
                tz=resource.tz,
                lang_code=resource.partner_id.lang,
            )
            allocated_hours = timedelta(hours=self.allocated_hours).total_seconds()
            formatted_allocated_hours = "%d:%02d" % (
                allocated_hours // 3600,
                round(allocated_hours % 3600 / 60),
            )
            allocated_percentage = float_repr(
                self.allocated_percentage, precision_digits=0
            )
            view_context.update(
                {
                    "iCal_url": self._get_ics_url(resource.partner_id),
                    "link": resource_url_map[resource.id],
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "recipient_name": resource.name,
                    "recipient_email": resource._get_planning_email(),
                    "allocated_hours": formatted_allocated_hours,
                    "allocated_percentage": allocated_percentage,
                    "unassign_deadline": unassign_deadline,
                }
            )
            mail_id = template.with_context(view_context).send_mail(
                self.id, email_layout_xmlid="mail.mail_notification_light"
            )
            mails_to_send_ids.append(mail_id)

        mails_to_send = self.env["mail.mail"].sudo().browse(mails_to_send_ids)
        if mails_to_send:
            mails_to_send.send()

        vals = {"publication_warning": False}
        if self.state == "1_draft":
            vals["state"] = "2_published"
        self.write(vals)
        return

    def _send_shift_assigned(self, slot, human_resource) -> None:
        email_from = slot.company_id.email or ""
        assignee = slot.resource_id.employee_id

        template = self.env.ref(
            "planning.email_template_shift_switch_email", raise_if_not_found=False
        )
        start_datetime = self._format_datetime_to_user_tz(
            slot.start_datetime,
            assignee.env,
            tz=assignee.tz,
            lang_code=assignee.partner_id.lang,
        )
        end_datetime = self._format_datetime_to_user_tz(
            slot.end_datetime,
            assignee.env,
            tz=assignee.tz,
            lang_code=assignee.partner_id.lang,
        )
        allocated_hours = float_repr(self.allocated_hours, precision_digits=2)
        allocated_percentage = float_repr(self.allocated_percentage, precision_digits=0)
        template_context = {
            "old_assignee_name": assignee.name,
            "new_assignee_name": human_resource.employee_id.name,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "allocated_hours": allocated_hours,
            "allocated_percentage": allocated_percentage,
        }
        if template and assignee != human_resource.employee_id:
            template.with_context(**template_context).send_mail(
                slot.id,
                email_values={
                    "email_to": assignee.work_email,
                    "email_from": email_from,
                },
                email_layout_xmlid="mail.mail_notification_light",
            )


    @api.model
    def _merge_slots_values(self, slots_to_merge, unforecastable_intervals):
        if not slots_to_merge:
            return slots_to_merge
        new_slots_vals_list = []
        sum_allocated_hours = 0
        to_merge = None
        common_allocated_percentage = slots_to_merge[0]["allocated_percentage"]
        resource_id = slots_to_merge[0].get("resource_id")
        start_datetime = slots_to_merge[0]["start_datetime"]
        previous_end_datetime = start_datetime
        for slot in slots_to_merge:
            mergeable = True
            if (
                not slot["start_datetime"]
                or common_allocated_percentage != slot["allocated_percentage"]
                or resource_id != slot["resource_id"]
                or (slot["start_datetime"] - previous_end_datetime).total_seconds()
                > 3600 * 24
            ):
                mergeable = False
            if mergeable:
                end_datetime = slot["end_datetime"]
                interval = Intervals(
                    [
                        (
                            start_datetime.replace(tzinfo=UTC),
                            end_datetime.replace(tzinfo=UTC),
                            self.env["resource.calendar.attendance"],
                        )
                    ]
                )
                if not (interval & unforecastable_intervals):
                    sum_allocated_hours += slot["allocated_hours"]
                    to_merge = {
                        **slot,
                        "start_datetime": start_datetime,
                        "allocated_hours": sum_allocated_hours,
                    }
                else:
                    mergeable = False
            if not mergeable:
                if to_merge:
                    new_slots_vals_list.append(to_merge)
                to_merge = slot
                start_datetime = slot["start_datetime"]
                common_allocated_percentage = slot["allocated_percentage"]
                resource_id = slot.get("resource_id")
                sum_allocated_hours = slot["allocated_hours"]
            previous_end_datetime = slot["end_datetime"]
        if to_merge:
            new_slots_vals_list.append(to_merge)
        return new_slots_vals_list

    def _get_working_hours_over_period(self, start_utc, end_utc, schedule):
        start = max(start_utc, self.start_datetime.replace(tzinfo=UTC))
        end = min(end_utc, self.end_datetime.replace(tzinfo=UTC))
        slot_interval = Intervals(
            [(start, end, self.env["resource.calendar.attendance"])]
        )

        if self.resource_id and self.resource_id._is_flexible():
            return schedule.work_hours(
                self.resource_id,
                slot_interval & schedule.intervals[self.resource_id.id],
            )

        period = self.end_datetime - self.start_datetime
        slot_duration = period.total_seconds() / 3600
        if not self.resource_id and self.allocation_type == "forecast":
            max_hours_per_day = self.company_id.resource_calendar_id.hours_per_day
            max_duration = (
                period.days + (1 if period.seconds else 0)
            ) * max_hours_per_day
            return round(min(slot_duration, max_duration), 2)

        working_intervals = (
            schedule.intervals[self.resource_id.id]
            if self.resource_id
            else schedule.calendar_intervals[self.company_id.resource_calendar_id.id]
        )
        return round(get_intervals_hours(slot_interval & working_intervals), 2)

    def _get_slot_resource_urls(self) -> dict:
        def get_url_dt(dt):
            return dt.astimezone(timezone(self._get_tz())).strftime("%Y%m%dT%H%M%S")

        ics_description_data = {
            "shift": self._prepare_ics_description_data(),
            "is_google_url": True,
        }
        return {
            "google_url": "https://www.google.com/calendar/render?"
            + url_encode(
                {
                    "action": "TEMPLATE",
                    "text": self.display_name or self.env._("New Shift"),
                    "dates": f"{get_url_dt(self.start_datetime)}/{get_url_dt(self.end_datetime)}",
                    "ctz": self._get_tz(),
                    "details": self.env["ir.qweb"]._render(
                        "planning.planning_shift_ics_description", ics_description_data
                    ),
                }
            ),
        }

    def _get_ics_url(self, partner) -> str:
        self.check_singleton()
        __, token = self.env["access.link"]._issue(
            self,
            partner=partner,
            role="view",
            cause="notification",
        )
        return f"/slot/{token}.ics"

    def _get_link_expiry(self) -> datetime:
        return max(self.end_datetime, fields.Datetime.now()) + timedelta(days=30)

    def _get_duration_over_period(
        self, start_utc, stop_utc, schedule, has_allocated_hours=True
    ):
        assert start_utc.tzinfo and stop_utc.tzinfo
        self.check_singleton()
        start, stop = start_utc.replace(tzinfo=None), stop_utc.replace(tzinfo=None)
        if (
            has_allocated_hours
            and self.start_datetime >= start
            and self.end_datetime <= stop
        ):
            return self.allocated_hours
        ratio = self.allocated_percentage / 100.0
        working_hours = self._get_working_hours_over_period(
            start_utc, stop_utc, schedule
        )
        return working_hours * ratio

    def _gantt_progress_bar_resource_id(self, res_ids, start, stop):
        start_naive, stop_naive = start.replace(tzinfo=None), stop.replace(tzinfo=None)

        resources = (
            self.env["resource.resource"]
            .with_context(active_test=False)
            .search([("id", "in", res_ids)])
        )
        planning_slots = self.env["planning.slot"].search(
            [
                ("resource_id", "in", res_ids),
                ("start_datetime", "<=", stop_naive),
                ("end_datetime", ">=", start_naive),
            ]
        )

        schedule = resources.sudo()._get_work_schedule(start, stop)
        resource_work_intervals = schedule.intervals
        calendar_work_intervals = schedule.calendar_intervals

        planned_hours_mapped = defaultdict(float)
        for slot in planning_slots:
            planned_hours_mapped[slot.resource_id.id] += slot._get_duration_over_period(
                start, stop, schedule
            )
        work_hours = {
            resource.id: schedule.work_hours(resource) for resource in resources
        }

        company_calendar = self.env.company.resource_calendar_id
        resource_work_intervals[False] = (
            calendar_work_intervals.get(company_calendar.id)
            or company_calendar._work_intervals_batch(start, stop)[False]
        )
        work_interval_per_resource = defaultdict(list)
        for (
            resource_id,
            resource_work_intervals_per_resource,
        ) in resource_work_intervals.items():
            for resource_work_interval in resource_work_intervals_per_resource:
                work_interval_per_resource[resource_id].append(
                    (
                        resource_work_interval[0].replace(tzinfo=UTC),
                        resource_work_interval[1].replace(tzinfo=UTC),
                    )
                )
        avg_hours_per_resource = {False: 0}
        for resource in set(resources):
            if resource._is_fully_flexible():
                avg_hours_per_resource[resource.id] = (
                    24
                )
            else:
                avg_hours_per_resource[resource.id] = resource.calendar_id.hours_per_day

        return {
            resource.id: {
                "resource_type": resource.type,
                "resource_color": resource.color,
                "has_several_roles": len(resource.role_ids) > 1,
                "value": planned_hours_mapped[resource.id],
                "max_value": work_hours.get(resource.id, 0.0),
                "employee_id": resource.employee_id.id,
                "is_flexible_hours": resource._is_flexible(),
                "is_fully_flexible_hours": resource._is_fully_flexible(),
                "work_intervals": work_interval_per_resource.get(resource.id, 0.0),
                "avg_hours": avg_hours_per_resource.get(resource.id, 0.0),
            }
            for resource in resources
        }

    def _gantt_progress_bar_role_id(self, res_ids, start, stop):
        roles = self.env["resource.role"].browse(res_ids).exists()
        return self._sum_gantt_progress_bar_per_resource(
            roles,
            self.env["resource.resource"].search([("role_ids", "in", roles.ids)]),
            "role_ids",
            start,
            stop,
        )

    def _gantt_progress_bar_department_id(self, res_ids, start, stop):
        departments = self.env["hr.department"].browse(res_ids).exists()
        return self._sum_gantt_progress_bar_per_resource(
            departments,
            self.env["resource.resource"].search(
                [("employee_id.department_id", "in", departments.ids)]
            ),
            "department_id",
            start,
            stop,
        )

    def _sum_gantt_progress_bar_per_resource(
        self, records, resources, resource_field, start, stop
    ):
        per_resource = self._gantt_progress_bar_resource_id(resources.ids, start, stop)
        progress_bar = {
            record.id: {"value": 0.0, "max_value": 0.0} for record in records
        }
        for resource in resources:
            values = per_resource.get(resource.id)
            if not values:
                continue
            for record in resource[resource_field] & records:
                progress_bar[record.id]["value"] += values["value"]
                progress_bar[record.id]["max_value"] += values["max_value"]
        return progress_bar

    def _gantt_progress_bar(self, field_name, res_ids, start, stop):
        if not self.env.user._is_internal():
            return {}
        start, stop = start.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
        if field_name == "resource_id":
            return dict(
                self._gantt_progress_bar_resource_id(res_ids, start, stop),
                warning=self.env._(
                    "This employee is not expected to work during this period, either because they do not have a current contract or because they are on leave."
                ),
            )
        if field_name == "role_id":
            return self._gantt_progress_bar_role_id(res_ids, start, stop)
        if field_name == "department_id":
            return self._gantt_progress_bar_department_id(res_ids, start, stop)
        raise NotImplementedError("This Progress Bar is not implemented.")

    def _prepare_shift_vals(self) -> dict:
        self.check_singleton()
        return {
            "resource_id": False,
            "end_datetime": self.end_datetime,
            "role_id": self.role_id.id,
            "company_id": self.company_id.id,
            "allocated_percentage": self.allocated_percentage,
            "name": self.name,
            "recurrency_id": self.recurrency_id.id,
            "repeat": self.repeat,
            "repeat_interval": self.repeat_interval,
            "repeat_unit": self.repeat_unit,
            "repeat_type": self.repeat_type,
            "repeat_until": self.repeat_until,
            "repeat_number": self.repeat_number,
            "template_id": self.template_id.id,
        }

    def undo_split_shift(self, start_datetime, end_datetime, resource_id) -> bool:
        if len(self) != 2:
            raise ValueError("This method must take two slots in argument.")
        initial_shift, copied_shift = self
        if not (initial_shift.exists() and copied_shift.exists()):
            return False
        initial_shift.start_datetime = start_datetime
        initial_shift.end_datetime = end_datetime
        initial_shift.resource_id = resource_id
        copied_shift.unlink()
        return True

    @api.model
    def _gantt_resource_employees_working_periods(self, groups, start_date, stop_date):
        if not self.env.user.has_group("planning.group_planning_manager"):
            return {}

        resource_ids = {
            group["resource_id"][0] for group in groups if group["resource_id"]
        }

        employee_ids = set()
        employee_id_to_ressource_id = {}
        working_periods = {}
        for resource in self.env["resource.resource"].browse(resource_ids):
            if not resource.employee_id:
                continue
            resource_id = resource.id
            employee_id = resource.employee_id.id
            employee_ids.add(employee_id)
            employee_id_to_ressource_id[employee_id] = resource_id
            working_periods[resource_id] = []

        if employee_ids:
            start, stop = (
                fields.Datetime.from_string(start_date),
                fields.Datetime.from_string(stop_date),
            )

            employees_sudo = self.env["hr.employee"].sudo().browse(employee_ids)
            employees_with_contract = dict(
                self.env["hr.version"]
                .sudo()
                ._read_group(
                    domain=[
                        ("employee_id", "in", employees_sudo.ids),
                        ("contract_date_start", "!=", False),
                    ],
                    groupby=["employee_id"],
                    aggregates=["__count"],
                )
            )
            contracts = employees_sudo._get_versions_with_contract_overlap_with_period(
                start.date(), stop.date()
            )
            employees_with_contract_in_current_scale = []
            for contract in contracts:
                employee_id = contract.employee_id.id
                end_datetime = (
                    contract.contract_date_end
                    and contract.contract_date_end
                    + relativedelta(hour=23, minute=59, second=59)
                )
                if end_datetime:
                    user_tz = timezone(
                        self.env.user.tz or self.env.context.get("tz") or "UTC"
                    )
                    end_datetime = wall_to_utc(end_datetime, user_tz)
                    end_datetime = fields.Datetime.to_string(end_datetime)
                employees_with_contract_in_current_scale.append(employee_id)
                working_periods[employee_id_to_ressource_id[employee_id]].append(
                    {
                        "start": fields.Datetime.to_string(
                            contract.contract_date_start
                        ),
                        "end": end_datetime,
                    }
                )
            for employee in employees_sudo - self.env["hr.employee"].browse(
                employees_with_contract_in_current_scale
            ):
                if employees_with_contract.get(employee):
                    continue
                working_periods[employee_id_to_ressource_id[employee.id]].append(
                    {
                        "start": start_date,
                        "end": stop_date,
                    }
                )
        return working_periods
