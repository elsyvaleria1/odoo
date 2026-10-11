from collections import defaultdict
from datetime import UTC, timedelta
from typing import Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.libs.numbers import float_compare, float_is_zero, float_round

_debug = DebugLog(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    def _domain_sale_line_id(self):
        return Domain.AND(
            [
                self.env["sale.order.line"]._get_domain_lines_sellable(),
                self.env["sale.order.line"]._domain_sale_line_service(),
            ]
        )

    start_datetime = fields.Datetime(required=False)
    end_datetime = fields.Datetime(required=False)
    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sales Order Item",
        index=True,
        group_expand="_group_expand_sale_line_id",
        domain=_domain_sale_line_id,
        ondelete="cascade",
        help="Sales order item for which this shift will be performed. When sales orders are automatically planned,"
        " the remaining hours of the sales order item, as well as the role defined on the service, are taken into account.",
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        related="sale_line_id.order_id",
        string="Sales Order",
    )
    sale_order_state = fields.Selection(
        related="sale_order_id.state",
        string="Sales Order State",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="sale_order_id.partner_id",
    )
    role_product_ids = fields.One2many(
        comodel_name="product.template",
        related="role_id.product_ids",
        export_string_translation=False,
    )
    sale_line_plannable = fields.Boolean(
        related="sale_line_id.product_id.planning_enabled",
        export_string_translation=False,
    )
    allocated_hours = fields.Float(compute_sudo=True)

    _check_datetimes_set_or_plannable_slot = models.Constraint(
        "CHECK((start_datetime IS NOT NULL AND end_datetime IS NOT NULL) OR sale_line_id IS NOT NULL)",
        "Only slots linked to a Sales Order with a plannable service can be unscheduled.",
    )

    @api.depends("sale_line_id")
    def _compute_role_id(self) -> None:
        slot_with_sol = self.filtered("sale_line_plannable")
        for slot in slot_with_sol:
            if not slot.role_id:
                slot.role_id = slot.sale_line_id.product_id.planning_role_id
        super(PlanningSlot, self - slot_with_sol)._compute_role_id()

    @api.depends(
        "start_datetime",
        "sale_line_id.planning_hours_to_plan",
        "sale_line_id.planning_hours_planned",
    )
    def _compute_allocated_hours(self) -> None:
        planned_slots = self.filtered("start_datetime")
        unplanned_slots = self - planned_slots
        if self.env.context.get("sale_planning_prevent_recompute"):
            self.env.remove_to_compute(
                self._fields["allocated_percentage"], unplanned_slots
            )
        else:
            for slot in unplanned_slots:
                if slot.sale_line_id:
                    slot.allocated_hours = max(
                        slot.sale_line_id.planning_hours_to_plan
                        - slot.sale_line_id.planning_hours_planned,
                        0.0,
                    )
        super(PlanningSlot, planned_slots)._compute_allocated_hours()
        if planned_slots:
            self.env.add_to_compute(
                self.env["sale.order.line"]._fields["planning_hours_planned"],
                self.sale_line_id,
            )

    def _compute_allocated_percentage(self) -> None:
        planned_slots = self.filtered("start_datetime")
        super(PlanningSlot, planned_slots)._compute_allocated_percentage()

    @api.depends("start_datetime")
    def _compute_past_shift(self) -> None:
        planned_slots = self.filtered("start_datetime")
        (self - planned_slots).is_past = False
        super(PlanningSlot, planned_slots)._compute_past_shift()

    @api.depends("start_datetime")
    def _compute_unassign_deadline(self) -> None:
        planned_slots = self.filtered("start_datetime")
        (self - planned_slots).unassign_deadline = False
        super(PlanningSlot, planned_slots)._compute_unassign_deadline()

    @api.depends("start_datetime")
    def _compute_is_unassign_deadline_passed(self) -> None:
        planned_slots = self.filtered("start_datetime")
        (self - planned_slots).is_unassign_deadline_passed = False
        super(PlanningSlot, planned_slots)._compute_is_unassign_deadline_passed()

    @api.depends("start_datetime", "sale_line_id")
    def _compute_template_autocomplete_ids(self) -> None:
        unplanned_sale_slots = self.filtered(
            lambda slot: slot.sale_line_id and not slot.start_datetime
        )
        for slot in unplanned_sale_slots:
            slot.template_autocomplete_ids = slot.template_id
        super(
            PlanningSlot, self - unplanned_sale_slots
        )._compute_template_autocomplete_ids()

    def _group_expand_sale_line_id(self, sale_lines, domain):
        dom_tuples = [
            (dom[0], dom[1])
            for dom in domain
            if isinstance(dom, (list, tuple)) and len(dom) == 3
        ]
        sale_line_ids = self.env.context.get("filter_sale_line_ids", False)
        if sale_line_ids:
            return sale_lines.search([("id", "in", sale_line_ids)])
        elif (
            self.env.context.get("planning_expand_sale_line_id")
            and ("start_datetime", "<=") in dom_tuples
            and ("end_datetime", ">=") in dom_tuples
        ):
            if ("sale_line_id", "=") in dom_tuples or (
                "sale_line_id",
                "ilike",
            ) in dom_tuples:
                filter_domain = self._expand_domain_m2o_groupby(domain, "sale_line_id")
                return sale_lines.search(filter_domain)
            filters = self._expand_domain_dates(domain)
            sale_lines = (
                self.env["planning.slot"].search(filters).mapped("sale_line_id")
            )
            return sale_lines.search([("id", "in", sale_lines.ids)])
        return sale_lines


    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if res.get("sale_line_id"):
            sale_line_id = self.env["sale.order.line"].browse(res.get("sale_line_id"))
            if (
                sale_line_id.product_id.planning_enabled
                and res.get("start_datetime")
                and res.get("end_datetime")
            ):
                remaining_hours_to_plan = (
                    sale_line_id.planning_hours_to_plan
                    - sale_line_id.planning_hours_planned
                )
                if float_compare(remaining_hours_to_plan, 0, precision_digits=2) < 1:
                    return res
                allocated_hours = (
                    res["end_datetime"] - res["start_datetime"]
                ).total_seconds() / 3600.0
                if (
                    float_compare(
                        remaining_hours_to_plan, allocated_hours, precision_digits=2
                    )
                    < 1
                ):
                    res["end_datetime"] = res["start_datetime"] + timedelta(
                        hours=remaining_hours_to_plan
                    )
        return res

    def _display_name_fields(self):
        return ["partner_id"] + super()._display_name_fields() + ["sale_line_id"]

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        _debug.lifecycle("create", slots=res, rows=len(vals_list))
        if res.sale_line_id:
            res.sale_line_id.sudo()._compute_planning_hours_planned()
            res.sale_line_id.sudo()._post_process_planning_sale_line(
                ids_to_exclude=res.ids
            )
        return res

    def write(self, vals):
        _debug.lifecycle("write", slots=self, fields=list(vals))
        self.update_slot_resource(vals)
        return True

    def update_slot_resource(self, vals):
        sale_order_slots_to_plan = []
        PlanningShift = self.env["planning.slot"]
        slots_to_write = PlanningShift
        slots_written = PlanningShift
        if vals.get("start_datetime"):
            slot_vals_list_per_employee = defaultdict(list)
            for slot in self:
                if slot.sale_line_plannable and not slot.start_datetime:
                    new_vals, tmp_sale_order_slots_to_plan, resource = (
                        slot._get_sale_order_slots_to_plan(
                            vals, slot_vals_list_per_employee
                        )
                    )
                    if new_vals:
                        super(PlanningSlot, slot).write(new_vals[0])
                        slots_written += slot
                        sale_order_slots_to_plan += tmp_sale_order_slots_to_plan
                        if resource:
                            slot_vals_list_per_employee[resource] += (
                                new_vals + tmp_sale_order_slots_to_plan
                            )
                else:
                    slots_to_write |= slot
        else:
            slots_to_write |= self

        super(PlanningSlot, slots_to_write).write(vals)
        slots_written += slots_to_write

        if sale_order_slots_to_plan:
            slots_written += self.create(sale_order_slots_to_plan)

        slots_to_unlink = PlanningShift
        slots_to_post_process = self
        for slot in self:
            if not slot.exists():
                slots_to_post_process -= slot
            elif (
                slot.sale_line_id
                and not slot.start_datetime
                and float_compare(slot.allocated_hours, 0.0, precision_digits=2) < 1
            ):
                slots_to_unlink += slot
        if (slots_to_post_process - slots_to_unlink).sale_line_id:
            (
                slots_to_post_process - slots_to_unlink
            ).sale_line_id.sudo()._post_process_planning_sale_line(
                ids_to_exclude=self.ids
            )
        slots_to_unlink.unlink()
        return slots_written - slots_to_unlink


    def action_view_sale_order(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "sale.action_sale_order"
        )
        action["views"] = [(False, "form")]
        action["res_id"] = self.sale_order_id.id
        return action


    def _get_domain_template_slots(self):
        domain = super()._get_domain_template_slots()
        if self.sale_line_plannable:
            domain = Domain.AND(
                [
                    domain,
                    [
                        "|",
                        (
                            "role_id",
                            "=",
                            self.sale_line_id.product_id.planning_role_id.id,
                        ),
                        ("role_id", "=", False),
                    ],
                ]
            )
        return domain

    def _get_sale_order_slots_to_plan(self, vals, slot_vals_list_per_resource) -> tuple:
        self.check_singleton()
        to_allocate = (
            self.sale_line_id.planning_hours_to_plan
            - self.sale_line_id.planning_hours_planned
        )
        if to_allocate < 0.0:
            return [], [], None
        work_intervals, unforecastable_intervals, resource, partial_interval_slots = (
            self.sudo()
            .with_context(
                default_end_datetime=self.env.context.get("default_end_datetime")
            )
            ._get_resource_work_info(vals, slot_vals_list_per_resource)
        )
        following_slots_vals_list = []
        if work_intervals:
            following_slots_vals_list = self._prepare_slots_vals_list(
                vals,
                work_intervals,
                partial_interval_slots,
                unforecastable_intervals,
                to_allocate=to_allocate,
                resource=resource,
            )
            if following_slots_vals_list:
                following_slots_vals_list = self._merge_slots_values(
                    following_slots_vals_list, unforecastable_intervals
                )
                return (
                    following_slots_vals_list[:1],
                    following_slots_vals_list[1:],
                    resource,
                )
        return [], [], resource

    def _prepare_slots_vals_list(
        self,
        vals,
        work_intervals,
        partial_interval_slots,
        unforecastable_intervals,
        to_allocate,
        resource,
    ) -> list[ValuesType]:
        self.check_singleton()
        following_slots_vals_list = []
        for interval in work_intervals:
            if float_compare(to_allocate, 0.0, precision_digits=2) < 1:
                break
            start_interval = interval[0].astimezone(UTC).replace(tzinfo=None)
            end_interval = interval[1].astimezone(UTC).replace(tzinfo=None)
            if partial_interval_slots[interval]:
                allocated_dict = defaultdict(float)
                allocated_dict.update(
                    {
                        start_interval: 0,
                        end_interval: 0,
                    }
                )
                for slot in partial_interval_slots[interval]:
                    allocated_dict[slot["start_datetime"]] += float_round(
                        slot["allocated_percentage"], precision_digits=1
                    )
                    allocated_dict[slot["end_datetime"]] += float_round(
                        -slot["allocated_percentage"], precision_digits=1
                    )
                datetime_list = list(allocated_dict.keys())
                datetime_list.sort()
                allocable = 100.0
                for i in range(1, len(datetime_list)):
                    start_dt = datetime_list[i - 1]
                    end_dt = datetime_list[i]
                    if i != len(datetime_list) - 1 and float_is_zero(
                        allocated_dict[datetime_list[i]], precision_digits=2
                    ):
                        datetime_list[i] = datetime_list[i - 1]
                        continue
                    allocable -= float_round(
                        allocated_dict[datetime_list[i - 1]], precision_digits=1
                    )
                    if float_compare(allocable, 0.0, precision_digits=2) < 1:
                        unforecastable_intervals |= Intervals(
                            [
                                (
                                    start_dt.replace(tzinfo=UTC),
                                    end_dt.replace(tzinfo=UTC),
                                    self.env["resource.schedule.exception"],
                                )
                            ]
                        )
                        continue
                    if end_dt <= start_interval or start_dt >= end_interval:
                        continue
                    start_dt = max(start_dt, start_interval)
                    end_dt = min(end_dt, end_interval)
                    end_dt = min(
                        end_dt,
                        start_dt + timedelta(hours=to_allocate * (100.0 / allocable)),
                    )
                    to_allocate -= ((end_dt - start_dt).total_seconds() / 3600.0) * (
                        allocable / 100.0
                    )
                    self._add_slot_to_list(
                        start_dt,
                        end_dt,
                        resource,
                        following_slots_vals_list,
                        allocable=allocable,
                    )
            else:
                end_dt = min(
                    start_interval + timedelta(hours=to_allocate), end_interval
                )
                to_allocate -= (end_dt - start_interval).total_seconds() / 3600.0
                self._add_slot_to_list(
                    start_interval, end_dt, resource, following_slots_vals_list
                )

        if (
            float_compare(to_allocate, 0.0, precision_digits=2) == 1
            and following_slots_vals_list
        ):
            planning_slot_values = self.sale_line_id._planning_slot_values()
            planning_slot_values.update(allocated_hours=to_allocate)
            following_slots_vals_list.append(planning_slot_values)

        return following_slots_vals_list

    def _add_slot_to_list(
        self,
        start_datetime,
        end_datetime,
        resource,
        following_slots_vals_list,
        allocable=100.0,
    ) -> None:
        if end_datetime <= start_datetime:
            return
        allocated_hours = ((end_datetime - start_datetime).total_seconds() / 3600.0) * (
            allocable / 100.0
        )
        following_slots_vals_list.append(
            {
                **self.sale_line_id._planning_slot_values(),
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
                "allocated_percentage": allocable,
                "allocated_hours": allocated_hours,
                "resource_id": resource.id,
            }
        )

    def _get_resource_work_info(self, vals, slot_vals_list_per_resource) -> tuple:
        self.check_singleton()
        assert self.env.context.get("default_end_datetime")
        start_dt = fields.Datetime.to_datetime(vals["start_datetime"]).replace(
            tzinfo=UTC
        )
        end_dt = fields.Datetime.to_datetime(
            self.env.context["default_end_datetime"]
        ).replace(tzinfo=UTC)
        resource_calendar_validity_intervals, resource = (
            self._get_slot_calendar_and_resource(vals, start_dt, end_dt)
        )
        attendance_intervals = Intervals()
        unavailability_intervals = Intervals()
        for (
            calendar,
            validity_intervals,
        ) in resource_calendar_validity_intervals.items():
            attendance = calendar._attendance_intervals_batch(
                start_dt, end_dt, resources=resource
            )[resource.id]
            leaves = calendar._leave_intervals_batch(
                start_dt, end_dt, resources=resource
            )[resource.id]
            attendance_intervals |= attendance & validity_intervals
            unavailability_intervals |= leaves & validity_intervals
        partial_slots = {}
        partial_interval_slots = defaultdict(list)
        if resource:
            slots = self.search_read(
                [
                    ("resource_id", "=", resource.id),
                    ("start_datetime", "<", end_dt.replace(tzinfo=None)),
                    ("end_datetime", ">", start_dt.replace(tzinfo=None)),
                ],
                ["start_datetime", "end_datetime", "allocated_percentage"],
            )
            slots += slot_vals_list_per_resource[resource]
            planning_slots_intervals = Intervals()
            partial_slots = []
            for slot in slots:
                if not slot["start_datetime"]:
                    continue
                if (
                    float_compare(
                        slot["allocated_percentage"], 100.0, precision_digits=0
                    )
                    < 0
                ):
                    partial_slots.append(slot)
                else:
                    interval = Intervals(
                        [
                            (
                                slot["start_datetime"].replace(tzinfo=UTC),
                                slot["end_datetime"].replace(tzinfo=UTC),
                                self.env["resource.schedule.exception"],
                            )
                        ]
                    )
                    planning_slots_intervals |= interval
            unavailability_intervals |= planning_slots_intervals
            work_intervals = attendance_intervals - unavailability_intervals
            if partial_slots:
                for interval in work_intervals:
                    for slot in partial_slots:
                        if (
                            slot["start_datetime"].replace(tzinfo=UTC) < interval[1]
                            and slot["end_datetime"].replace(tzinfo=UTC) > interval[0]
                        ):
                            partial_interval_slots[interval].append(slot)
        else:
            work_intervals = attendance_intervals - unavailability_intervals
        return (
            work_intervals,
            unavailability_intervals,
            resource,
            partial_interval_slots,
        )

    def _get_slot_calendar_and_resource(self, vals, start, end) -> tuple:
        self.check_singleton()
        resource = self.resource_id
        if vals.get("resource_id"):
            resource = self.env["resource.resource"].browse(vals.get("resource_id"))
        resource_calendar_validity_intervals = (
            resource._get_calendars_validity_within_period(
                start, end, default_company=self.company_id
            )[resource.id]
        )
        return resource_calendar_validity_intervals, resource

    def _prepare_ics_description_data(self) -> dict:
        return {
            **super()._prepare_ics_description_data(),
            "sale_order": self.sale_line_id.sudo().order_id.name
            if self.sale_line_id
            else "",
            "sale_order_item": self.sale_line_id.sudo().name
            if self.sale_line_id
            else "",
            "partner": self.partner_id.name,
        }


    @api.model
    def _get_employee_to_assign_priority_list(self) -> list:
        return ["previous_slot", "closest_so_line_slot", "default_role", "roles"]

    def _get_employee_per_priority(self, priority, employee_ids_to_exclude, cache):
        if priority in cache:
            return cache[priority].pop(0) if cache.get(priority) else None
        if priority == "previous_slot":
            search = self._read_group(
                [
                    ("sale_line_id", "=", self.sale_line_id.id),
                    ("employee_id", "!=", False),
                    ("start_datetime", "!=", False),
                    ("employee_id", "not in", employee_ids_to_exclude),
                ],
                ["employee_id"],
                order="end_datetime:max desc, employee_id",
            )
            cache[priority] = [employee.id for [employee] in search]
        elif priority == "closest_so_line_slot":
            closest_slots = self.search(
                [
                    ("sale_line_id.product_id", "=", self.sale_line_id.product_id.id),
                    (
                        "sale_line_id.order_id.partner_id",
                        "=",
                        self.sale_line_id.order_id.partner_id.id,
                    ),
                    ("employee_id", "!=", False),
                    ("start_datetime", "!=", False),
                    ("employee_id", "not in", employee_ids_to_exclude),
                ]
            )
            now = fields.Datetime.now()
            closest_slots = closest_slots.sorted(
                key=lambda s: abs(s.end_datetime - now)
            )
            cache[priority] = closest_slots.employee_id.ids
        elif priority == "default_role":
            search = (
                self.env["hr.employee"]
                .sudo()
                .search(
                    [
                        ("default_planning_role_id", "=", self.role_id.id),
                        ("id", "not in", employee_ids_to_exclude),
                    ]
                )
            )
            cache[priority] = search.ids
        elif priority == "roles":
            search = self.env["hr.employee"].search(
                [
                    ("planning_role_ids", "=", self.role_id.id),
                    ("id", "not in", employee_ids_to_exclude),
                ]
            )
            cache[priority] = search.ids
        return cache[priority].pop(0) if cache.get(priority) else None

    def _get_employee_to_assign(
        self, default_priority, employee_ids_to_exclude, cache, employee_per_sol
    ) -> tuple:
        self.check_singleton()
        if self.sale_line_id.id in employee_per_sol:
            employee_id = next(
                (
                    employee_id
                    for employee_id in employee_per_sol[self.sale_line_id.id]
                    if employee_id not in employee_ids_to_exclude
                ),
                None,
            )
            return employee_id, default_priority
        priority_list = self._get_employee_to_assign_priority_list()
        for priority in priority_list:
            if not default_priority or priority == default_priority:
                default_priority = None
                employee_id = self._get_employee_per_priority(
                    priority, employee_ids_to_exclude, cache
                )
                if employee_id:
                    return employee_id, priority
        return None, None

    @api.model
    def _get_ordered_slots_to_assign(self, domain) -> Self:
        return self.search(domain, order="sale_line_id desc")

    @api.model
    def _get_employee_per_sol_within_period(self, slots, start, end) -> dict:
        assert start and end
        end = fields.Datetime.to_datetime(end)

        employee_per_sol = self.env["planning.slot"]._read_group(
            [
                ("sale_line_id", "in", slots.sale_line_id.ids),
                ("start_datetime", "<", end),
                ("end_datetime", ">", start),
                ("employee_id", "!=", False),
            ],
            ["sale_line_id"],
            ["employee_id:array_agg"],
        )

        return {
            sale_line.id: employee_ids for sale_line, employee_ids in employee_per_sol
        }

    def _get_domain_shifts_to_plan(self, view_domain=None):
        if view_domain:
            domain = Domain(view_domain).map_conditions(
                lambda cond: (
                    Domain(cond.field_expr, "=", False)
                    if cond.field_expr in ("start_datetime", "end_datetime")
                    else cond
                )
            )
        else:
            domain = Domain("start_datetime", "=", False)
        domain &= Domain("sale_line_id", "!=", False)
        if self.env.context.get("planning_gantt_active_sale_order_id"):
            domain &= Domain(
                "sale_order_id",
                "=",
                self.env.context.get("planning_gantt_active_sale_order_id"),
            )
        return domain

    def auto_plan_id(self):
        self.check_singleton()
        if self.sale_order_id.state == "cancel":
            return self._get_notification_action(
                "danger",
                self.env._(
                    "You are attempting to create a slot for a cancelled sales order."
                ),
            )
        return super().auto_plan_id()

    @api.model
    def auto_plan_ids(self, view_domain):
        res = super().auto_plan_ids(view_domain)
        if self.env.context.get("planning_slot_id"):
            res["sale_line_planned"] = []
            return res
        slots_to_assign = self._get_ordered_slots_to_assign(
            self._get_domain_shifts_to_plan(view_domain)
        )
        start_datetime = max(
            fields.Datetime.to_datetime(self.env.context.get("default_start_datetime")),
            fields.Datetime.now().replace(hour=0, minute=0, second=0),
        )
        employee_per_sol = self._get_employee_per_sol_within_period(
            slots_to_assign,
            start_datetime,
            self.env.context.get("default_end_datetime"),
        )
        PlanningShift = self.env["planning.slot"]
        slots_assigned = PlanningShift
        employee_ids_to_exclude = []

        for slot in slots_to_assign:
            slot_assigned = PlanningShift
            previous_priority = None
            cache = {}
            while not slot_assigned:
                employee_id, previous_priority = slot._get_employee_to_assign(
                    previous_priority, employee_ids_to_exclude, cache, employee_per_sol
                )
                if not employee_id:
                    break
                employee = self.env["hr.employee"].browse(employee_id)
                vals = {
                    "start_datetime": start_datetime,
                    "end_datetime": start_datetime + timedelta(days=1),
                    "resource_id": employee.resource_id.id,
                }
                slot_assigned = slot.update_slot_resource(vals)
                if not slot_assigned:
                    employee_ids_to_exclude.append(employee_id)
            slots_assigned += slot_assigned

        res["sale_line_planned"] = slots_assigned.ids
        return res

    @api.model
    def action_rollback_auto_plan_ids(self, shifts_data) -> None:
        self.browse(shifts_data["sale_line_planned"]).action_unschedule()
        super().action_rollback_auto_plan_ids(shifts_data)


    def _init_remaining_hours_to_plan(self, remaining_hours_to_plan):
        self.check_singleton()
        res = super()._init_remaining_hours_to_plan(remaining_hours_to_plan)
        if self.sale_line_id.product_id.planning_enabled:
            if self.sale_line_id not in remaining_hours_to_plan:
                self.sale_line_id._compute_planning_hours_planned()
                remaining_hours_to_plan[self.sale_line_id] = (
                    self.sale_line_id.planning_hours_to_plan
                    - self.sale_line_id.planning_hours_planned
                )
            if (
                float_compare(
                    remaining_hours_to_plan[self.sale_line_id], 0.0, precision_digits=2
                )
                != 1
            ):
                return False
        return res

    def _update_remaining_hours_to_plan_and_values(
        self, remaining_hours_to_plan, values
    ):
        if self.allocated_percentage and self.sale_line_id.product_id.planning_enabled:
            if (
                float_compare(
                    remaining_hours_to_plan[self.sale_line_id], 0.0, precision_digits=2
                )
                != 1
            ):
                return False
            allocated_hours = (
                values["end_datetime"] - values["start_datetime"]
            ).total_seconds() / 3600
            ratio = self.allocated_percentage / 100.00
            remaining_hours = min(
                remaining_hours_to_plan[self.sale_line_id] / ratio, allocated_hours
            )
            values["end_datetime"] = values["start_datetime"] + timedelta(
                hours=remaining_hours
            )
            values.pop("allocated_hours", None)
            remaining_hours_to_plan[self.sale_line_id] -= remaining_hours * ratio
        return True

    def action_unschedule(self):
        unfinished_slots = self.filtered(
            lambda slot: (
                slot.sale_line_id.product_id.planning_enabled
                and (
                    slot.sale_line_id.planning_hours_to_plan
                    - slot.sale_line_id.planning_hours_planned
                    > 0.0
                )
            )
        )
        remaining = self
        if unfinished_slots:
            unscheduled_slots = unfinished_slots.search(
                [
                    ("id", "not in", unfinished_slots.ids),
                    ("sale_line_id", "in", unfinished_slots.sale_line_id.ids),
                    ("start_datetime", "=", False),
                ]
            )
            lines_already_unscheduled = unscheduled_slots.sale_line_id
            slots_to_unlink = unfinished_slots.filtered(
                lambda shift: shift.sale_line_id in lines_already_unscheduled
            )
            remaining = self - slots_to_unlink
            slots_to_unlink.unlink()
            if len(remaining) == 1:
                return {"type": "ir.actions.act_window_close"}
        return remaining.write(
            {
                "start_datetime": False,
                "end_datetime": False,
                "employee_id": False,
            }
        )

    def _gantt_progress_bar_sale_line_id(self, res_ids) -> dict:
        if not self.env["sale.order.line"].has_access("read"):
            return {}
        return {
            sol.id: {
                "value": sol.planning_hours_planned,
                "max_value": sol.planning_hours_to_plan,
            }
            for sol in self.env["sale.order.line"].search([("id", "in", res_ids)])
        }

    def _gantt_progress_bar(self, field_name, res_ids, start, stop):
        if field_name == "sale_line_id":
            return dict(
                self._gantt_progress_bar_sale_line_id(res_ids),
                warning=self.env._(
                    "This Sale Order Item doesn't have a target value of planned hours."
                ),
            )
        return super()._gantt_progress_bar(field_name, res_ids, start, stop)

    def _prepare_shift_vals(self) -> dict:
        return {
            **super()._prepare_shift_vals(),
            "sale_line_id": self.sale_line_id.id,
        }

    def _gantt_progress_bar_resource_id(self, res_ids, start, stop):
        results = super()._gantt_progress_bar_resource_id(res_ids, start, stop)
        resource_per_id = {
            r.id: r for r in self.env["resource.resource"].browse(list(results.keys()))
        }
        for key, val in results.items():
            resource = resource_per_id[key]
            val["role_ids"] = resource.role_ids.ids
        return results

    def _print_planning_get_fields_to_copy(self):
        return super()._print_planning_get_fields_to_copy() + ["sale_line_id"]

    def _print_planning_get_slot_title(self, slot_start, slot_end, tz_info, group_by):
        res = super()._print_planning_get_slot_title(
            slot_start, slot_end, tz_info, group_by
        )

        if group_by != "sale_line_id" and self.sale_line_id:
            res += " - " + self.sale_line_id.display_name

        return res
