from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _timesheet_create_task(self, project):
        self.check_singleton()
        template = self.product_id.worksheet_template_id
        if template:
            return super(
                SaleOrderLine,
                self.with_context(default_worksheet_template_id=template.id),
            )._timesheet_create_task(project)
        else:
            return super()._timesheet_create_task(project)
