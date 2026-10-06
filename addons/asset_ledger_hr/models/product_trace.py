from odoo import api, fields, models


class ProductTrace(models.Model):
    _inherit = "product.trace"

    asset_manager_id = fields.Many2one(
        related="asset_id.manager_employee_id",
        readonly=False,
    )
    operator_id = fields.Many2one(
        related="asset_id.operator_employee_id",
        readonly=False,
    )
    future_operator_id = fields.Many2one(
        related="asset_id.future_operator_employee_id",
        readonly=False,
    )
    date_future_operator = fields.Datetime(
        related="asset_id.date_future_operator",
        readonly=False,
    )

    @api.model
    def _asset_ledger_field_map(self):
        return super()._asset_ledger_field_map() | {
            "operator_id": "operator_employee_id",
            "asset_manager_id": "manager_employee_id",
            "future_operator_id": "future_operator_employee_id",
            "date_future_operator": "date_future_operator",
        }

    def write(self, vals):
        resources_before = (
            self.filtered("asset_id").asset_id.sudo().resource_id
            if "asset_id" in vals
            else self.env["resource.resource"]
        )
        res = super().write(vals)
        if "asset_id" in vals:
            kept = self.filtered("asset_id").asset_id.sudo().resource_id
            (resources_before - kept)._end_custody()
        return res

    def unlink(self):
        self.filtered("asset_id").asset_id.sudo().resource_id._end_custody()
        return super().unlink()

    def action_view_logs_assignation(self):
        self.check_singleton()
        return self.asset_id.action_view_logs_assignation()

    def action_accept_operator_change(self):
        return self.asset_id.action_accept_operator_change()
