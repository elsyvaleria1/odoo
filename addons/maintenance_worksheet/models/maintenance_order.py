from odoo import api, fields, models
from odoo.exceptions import UserError


class MaintenanceOrder(models.Model):
    _inherit = "maintenance.order"

    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        domain="[('res_model', '=', 'maintenance.order'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Create templates for each type of order you have and customize their content with your own custom fields.",
    )
    worksheet_count = fields.Integer(compute="_compute_worksheet_count")

    @api.depends("worksheet_template_id")
    def _compute_worksheet_count(self) -> None:
        for record in self:
            count = 0
            if record.worksheet_template_id:
                x_model = self.env[record.worksheet_template_id.sudo().model_id.model]
                count = x_model.search_count(
                    [("x_maintenance_order_id", "=", record.id)]
                )
            record.worksheet_count = count

    def action_maintenance_worksheet(self):
        self.check_singleton()
        if not self.worksheet_template_id:
            raise UserError(self.env._("Please select a Worksheet Template."))
        action = self.worksheet_template_id.action_id.sudo().read()[0]
        x_model = self.env[self.worksheet_template_id.sudo().model_id.model]
        worksheet = x_model.search([("x_maintenance_order_id", "=", self.id)])
        context = self.env["ir.actions.actions"]._eval_action_context(
            action.get("context", "{}")
        )
        action.update(
            {
                "res_id": worksheet.id if worksheet else False,
                "views": [(False, "form")],
                "context": {
                    **context,
                    "edit": True,
                    "default_x_maintenance_order_id": self.id,
                },
            }
        )
        return action
