from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    planning_hours_planned = fields.Float(
        export_string_translation=False,
        compute="_compute_planning_hours",
    )
    planning_hours_to_plan = fields.Float(
        export_string_translation=False,
        compute="_compute_planning_hours",
    )
    planning_first_sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        export_string_translation=False,
        compute="_compute_planning_first_sale_line_id",
    )
    planning_initial_date = fields.Date(
        export_string_translation=False,
        compute="_compute_planning_initial_date",
    )

    @api.depends(
        "line_ids.planning_hours_to_plan",
        "line_ids.planning_hours_planned",
        "line_ids.product_id.planning_enabled",
    )
    def _compute_planning_hours(self) -> None:
        group_data = self.env["sale.order.line"]._read_group(
            [
                ("order_id", "in", self.ids),
                ("product_id.planning_enabled", "=", True),
            ],
            ["order_id"],
            ["planning_hours_to_plan:sum", "planning_hours_planned:sum"],
        )
        data_by_order = {
            order: (to_plan_sum, planned_sum)
            for order, to_plan_sum, planned_sum in group_data
        }
        for order in self:
            to_plan_sum, planned_sum = data_by_order.get(order._origin) or (0, 0)
            order.planning_hours_planned = planned_sum
            order.planning_hours_to_plan = to_plan_sum - planned_sum

    @api.depends(
        "line_ids.product_id.planning_enabled",
        "line_ids.planning_hours_to_plan",
        "line_ids.planning_hours_planned",
    )
    def _compute_planning_first_sale_line_id(self) -> None:
        planning_sol = self.env["sale.order.line"].search(
            [
                ("order_id", "in", self.ids),
                ("product_id.planning_enabled", "=", True),
                ("planning_hours_to_plan", ">", 0),
            ]
        )
        mapped_data = defaultdict(lambda: self.env["sale.order.line"])
        for sol in planning_sol:
            if not mapped_data[sol.order_id]:
                if sol.planning_hours_to_plan > sol.planning_hours_planned:
                    mapped_data[sol.order_id] = sol
        for order in self:
            order.planning_first_sale_line_id = mapped_data[order]

    @api.depends("line_ids.planning_slot_ids.start_datetime")
    def _compute_planning_initial_date(self) -> None:
        group_data = self.env["planning.slot"]._read_group(
            [("sale_order_id", "in", self.ids)],
            ["sale_order_id"],
            ["start_datetime:min"],
        )
        mapped_data = {
            sale_order.id: start_datetime_min
            for sale_order, start_datetime_min in group_data
        }
        for order in self:
            if mapped_data.get(order.id):
                order.planning_initial_date = mapped_data[order.id].date()
            else:
                order.planning_initial_date = fields.Date.today()

    @api.constrains("company_id")
    def _check_company_id(self) -> None:
        for order, slots in self.env["planning.slot"]._read_group(
            domain=[("sale_order_id", "in", self.ids)],
            groupby=["sale_order_id"],
            aggregates=["id:recordset"],
        ):
            if not order.company_id:
                continue
            different_company_slots = slots.filtered_domain(
                [("company_id", "!=", order.company_id.id)]
            )
            if not different_company_slots:
                continue
            _debug.logic(
                "company_change_refused",
                order=order,
                reason="shifts_in_other_company",
                slots=different_company_slots,
            )
            raise UserError(
                self.env._(
                    "You cannot update the company for sales order %(order_name)s as it's linked to shifts in another company.\n"
                    "Please transfer shifts %(slots_names)s to the destination company first.",
                    order_name=order.name,
                    slots_names=[slot.display_name for slot in different_company_slots],
                )
            )


    def _action_cancel(self):
        result = super()._action_cancel()
        self.sudo()._unplanned_shift_deletion()
        return result

    def _action_confirm(self):
        result = super()._action_confirm()
        _debug.pipeline("planning_generation_on_confirm", orders=self)
        self.line_ids.sudo()._planning_slot_generation()
        return result

    def action_view_planning(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "planning.planning_action_schedule_by_resource"
        )
        action.update(
            {
                "name": self.env._("View Planning"),
                "domain": [
                    (
                        "role_id",
                        "in",
                        self.line_ids.product_template_id.planning_role_id.ids,
                    )
                ],
                "context": {
                    "default_sale_line_id": self.planning_first_sale_line_id.id,
                    "search_default_group_by_resource": 1,
                    "initialDate": self.planning_initial_date,
                    "planning_gantt_active_sale_order_id": self.id,
                },
            }
        )
        return action

    def _unplanned_shift_deletion(self) -> None:
        unplanned_shift = self.env["planning.slot"].search(
            [
                ("sale_order_id", "in", self.ids),
                "|",
                ("start_datetime", "=", False),
                ("resource_id", "=", False),
            ]
        )
        _debug.lifecycle("unplanned_shifts_removed", orders=self, slots=unplanned_shift)
        unplanned_shift.unlink()
