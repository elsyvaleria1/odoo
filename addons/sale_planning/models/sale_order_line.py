from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import (
    float_compare,
    float_is_zero,
    float_round,
    format_duration,
    frozendict,
)

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    planning_slot_ids = fields.One2many(
        comodel_name="planning.slot",
        inverse_name="sale_line_id",
        export_string_translation=False,
    )
    planning_hours_planned = fields.Float(
        export_string_translation=False,
        compute="_compute_planning_hours_planned",
        compute_sudo=True,
        store=True,
    )
    planning_hours_to_plan = fields.Float(
        export_string_translation=False,
        compute="_compute_planning_hours_to_plan",
        compute_sudo=True,
        store=True,
    )

    @api.depends("product_uom_id", "product_uom_qty", "state")
    def _compute_planning_hours_to_plan(self) -> None:
        sol_planning = self.filtered_domain([("state", "not in", ["draft", "sent"])])
        if sol_planning:
            uom_hour = self.env.ref("base.product_uom_hour")
            uom_unit = self.env.ref("base.product_uom_unit")
            for sol in sol_planning:
                if sol.product_uom_id in (uom_hour, uom_unit):
                    sol.planning_hours_to_plan = sol.product_uom_qty
                else:
                    sol.planning_hours_to_plan = float_round(
                        sol.product_uom_id._get_quantity_estimate(
                            sol.product_uom_qty, uom_hour
                        ),
                        precision_digits=2,
                    )
        for line in self - sol_planning:
            line.planning_hours_to_plan = 0.0

    @api.depends("planning_slot_ids.allocated_hours", "state")
    def _compute_planning_hours_planned(self) -> None:
        PlanningSlot = self.env["planning.slot"]
        sol_planning = self.filtered_domain([("state", "not in", ["draft", "sent"])])

        group_data = PlanningSlot.with_context(
            sale_planning_prevent_recompute=True
        )._read_group(
            [
                ("sale_line_id", "in", sol_planning.ids),
                ("start_datetime", "!=", False),
            ],
            ["sale_line_id"],
            ["allocated_hours:sum"],
        )
        mapped_data = {
            sale_line.id: allocated_hours_sum
            for sale_line, allocated_hours_sum in group_data
        }
        for line in self:
            line.planning_hours_planned = mapped_data.get(line.id, 0.0)

        self.env.add_to_compute(
            PlanningSlot._fields["allocated_hours"],
            PlanningSlot.search(
                [
                    ("start_datetime", "=", False),
                    ("sale_line_id", "in", self.ids),
                ]
            ),
        )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if self.env.context.get("planning_slot_generation", True):
            sale_lines = lines.filtered(
                lambda sol: sol.state == "done" and not sol.is_expense
            )
            sale_lines._planning_slot_generation()
        return lines

    def write(self, vals):
        res = super().write(vals)
        self.filtered(lambda sol: not sol.is_expense)._post_process_planning_sale_line()
        return res

    @api.depends("product_id", "planning_hours_to_plan", "planning_hours_planned")
    @api.depends_context("with_planning_remaining_hours")
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.env.context.get("with_planning_remaining_hours"):
            return
        remaining = self.env._("remaining")
        for line in self:
            name = line.display_name
            if line.product_id.planning_enabled:
                remaining_hours = (
                    line.planning_hours_to_plan - line.planning_hours_planned
                )
                name = f"{name} ({format_duration(remaining_hours)} {remaining})"
            line.display_name = name

    def _post_process_planning_sale_line(self, ids_to_exclude=None) -> None:
        sol_planning = self.filtered("product_id.planning_enabled")
        if sol_planning:
            unscheduled_slots = (
                self.env["planning.slot"]
                .sudo()
                .search(
                    [
                        ("sale_line_id", "in", sol_planning.ids),
                        ("start_datetime", "=", False),
                    ]
                )
            )
            sol_with_unscheduled_slot = set()
            slots_to_unlink = self.env["planning.slot"]
            for slot in unscheduled_slots:
                if slot.sale_line_id.id in sol_with_unscheduled_slot:
                    slots_to_unlink |= slot
                else:
                    sol_with_unscheduled_slot.add(slot.sale_line_id.id)
                    if float_is_zero(slot.allocated_hours, precision_digits=2):
                        slots_to_unlink |= slot
            _debug.lifecycle(
                "duplicate_unscheduled_slots_removed",
                lines=sol_planning,
                unscheduled=unscheduled_slots,
                removed=slots_to_unlink,
            )
            slots_to_unlink.unlink()

    def _planning_slot_generation(self) -> None:
        vals_list_per_sol = self.filtered(
            lambda sol: sol._is_planning_slot_required()
        )._planning_slot_vals_list_per_sol()
        vals_list = [
            vals for vals_list in vals_list_per_sol.values() for vals in vals_list
        ]
        _debug.pipeline(
            "planning_slots_generated",
            lines=self,
            with_slots=len(vals_list_per_sol),
            slots=len(vals_list),
        )
        self.env["planning.slot"].create(vals_list)

    def _is_planning_slot_required(self) -> bool:
        return bool(
            self.product_id.type == "service"
            and self.product_id.planning_enabled
            and not self.planning_slot_ids.filtered(
                lambda shift: not shift.start_datetime
            )
            and float_compare(
                self.planning_hours_to_plan,
                self.planning_hours_planned,
                precision_digits=2,
            )
            == 1
        )

    def _planning_slot_vals_list_per_sol(self):
        return {sol: [sol._planning_slot_values()] for sol in self}

    def _planning_slot_values(self):
        return {
            "start_datetime": False,
            "end_datetime": False,
            "role_id": self.product_id.planning_role_id.id,
            "sale_line_id": self.id,
            "allocated_hours": self.planning_hours_to_plan
            - self.planning_hours_planned,
            "allocated_percentage": 100,
            "company_id": self.company_id.id,
        }
