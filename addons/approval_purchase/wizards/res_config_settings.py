from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    po_validation_level = fields.Selection(
        related="company_id.po_validation_level",
        readonly=False,
    )
    po_validation_amount = fields.Monetary(
        related="company_id.po_validation_amount",
        currency_field="company_currency_id",
        readonly=False,
    )
    po_auto_confirm_on_approval = fields.Boolean(
        related="company_id.po_auto_confirm_on_approval",
        readonly=False,
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Company Currency",
        readonly=True,
    )

    po_rate_limit_enabled = fields.Boolean(
        related="company_id.po_rate_limit_enabled",
        readonly=False,
    )
    po_rate_limit_hours = fields.Integer(
        related="company_id.po_rate_limit_hours",
        readonly=False,
    )
    po_rate_limit_count = fields.Integer(
        related="company_id.po_rate_limit_count",
        readonly=False,
    )
    po_rate_limit_amount = fields.Monetary(
        related="company_id.po_rate_limit_amount",
        currency_field="company_currency_id",
        readonly=False,
    )

    def action_view_po_approval_categories(self) -> dict:
        return {
            "name": self.env._("Purchase Approval Categories"),
            "type": "ir.actions.act_window",
            "res_model": "approval.category",
            "view_mode": "list,form",
            "domain": [
                ("approval_type", "=", "purchase"),
                ("company_id", "in", (self.company_id.id, False)),
            ],
            "context": {
                "default_approval_type": "purchase",
                "approval_category_routes_by_steps": True,
                "default_company_id": self.company_id.id,
            },
        }
