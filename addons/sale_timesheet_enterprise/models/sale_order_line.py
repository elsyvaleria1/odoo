from odoo import api, models
from odoo.fields import Domain

DEFAULT_INVOICED_TIMESHEET = "all"


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["sale.order.line", "mixin.timesheet.grid"]

    @api.depends("analytic_line_ids.validated")
    def _compute_qty_transferred(self):
        super()._compute_qty_transferred()

    def _timesheet_create_project_prepare_values(self):
        """Generate project values"""
        values = super()._timesheet_create_project_prepare_values()
        values["allow_timesheets"] = True
        return values

    def _timesheet_compute_delivered_quantity_domain(self):
        domain = super()._timesheet_compute_delivered_quantity_domain()
        # force to use only the validated timesheet
        param_invoiced_timesheet = self.env.registry.settings.get(
            self.env, "sale.invoiced_timesheet", DEFAULT_INVOICED_TIMESHEET
        )
        if param_invoiced_timesheet == "approved":
            domain = Domain.AND([domain, [("validated", "=", True)]])
        return domain

    def get_allocated_hours_field(self) -> str:
        return "product_uom_qty"

    def get_fields_worked_hours(self) -> list:
        return ["qty_transferred"]

    def get_domain_planned_and_worked_hours(self):
        return super().get_domain_planned_and_worked_hours() + [
            ("qty_transferred_method", "not in", ["manual", "milestones"])
        ]
