from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.resource_utils import filter_domain_leaf

_debug = DebugLog(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    sale_line_id = fields.Many2one(
        compute="_compute_sale_line_id",
        store=True,
        readonly=False,
    )

    @api.depends("sale_line_id.project_id", "sale_line_id.task_id.project_id")
    def _compute_project_id(self) -> None:
        slot_without_sol_project = self.env["planning.slot"]
        for slot in self:
            if (
                not slot.project_id
                and slot.sale_line_id
                and (
                    slot.sale_line_id.project_id or slot.sale_line_id.task_id.project_id
                )
            ):
                slot.project_id = (
                    slot.sale_line_id.task_id.project_id or slot.sale_line_id.project_id
                )
            else:
                slot_without_sol_project |= slot
        _debug.logic(
            "slot_project_from_sale_line",
            slots=self,
            from_sale_line=len(self) - len(slot_without_sol_project),
            delegated=slot_without_sol_project,
        )
        super(PlanningSlot, slot_without_sol_project)._compute_project_id()

    @api.depends("project_id")
    def _compute_sale_line_id(self) -> None:
        for slot in self:
            if not slot.sale_line_id and slot.project_id:
                slot.sale_line_id = slot.project_id.sale_line_id

    # ORM Override

    def _display_name_fields(self):
        """List of fields that can be displayed in the display_name"""
        # Ensure this will be displayed in the right order
        display_name_fields = [
            item
            for item in super()._display_name_fields()
            if item not in ["sale_line_id", "project_id"]
        ]
        return display_name_fields + ["project_id", "sale_line_id"]

    # Business methods

    def _get_domain_shifts_to_plan(self, view_domain=None):
        domain = super()._get_domain_shifts_to_plan(view_domain)
        if self.env.context.get("default_project_id"):
            domain = Domain(
                filter_domain_leaf(domain, lambda field: field != "project_id")
            )
            project = self.env["project.project"].browse(
                self.env.context.get("default_project_id")
            )
            sale_order_lines = project._get_sale_order_items(
                {"project.task": [("is_closed", "=", False)]}
            )
            _debug.logic(
                "shifts_to_plan_scoped_to_project",
                project=project,
                sale_lines=len(sale_order_lines),
                orders=len(sale_order_lines.order_id),
            )
            domain &= Domain("sale_order_id", "in", sale_order_lines.order_id.ids)
        return domain
