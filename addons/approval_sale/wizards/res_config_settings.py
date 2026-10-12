from typing import Any

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    so_validation_level = fields.Selection(
        related="company_id.so_validation_level",
        string="Sales Validation Level",
        readonly=False,
    )
    so_validation_amount = fields.Monetary(
        related="company_id.so_validation_amount",
        string="Sales Approval Threshold",
        currency_field="company_currency_id",
        readonly=False,
    )
    so_auto_confirm_on_approval = fields.Boolean(
        related="company_id.so_auto_confirm_on_approval",
        string="Sales Auto-Confirm When Approved",
        readonly=False,
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Company Currency",
        readonly=True,
    )

    so_rate_limit_enabled = fields.Boolean(
        related="company_id.so_rate_limit_enabled",
        readonly=False,
    )
    so_rate_limit_hours = fields.Integer(
        related="company_id.so_rate_limit_hours",
        readonly=False,
    )
    so_rate_limit_count = fields.Integer(
        related="company_id.so_rate_limit_count",
        readonly=False,
    )
    so_rate_limit_amount = fields.Monetary(
        related="company_id.so_rate_limit_amount",
        currency_field="company_currency_id",
        readonly=False,
    )

    def action_view_pending_so_approvals(self) -> dict[str, Any]:
        return {
            "name": self.env._("Pending Sales Approvals"),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("approval_state", "=", "pending"),
            ],
            "context": {"create": False},
        }

    def action_view_so_approval_categories(self) -> dict[str, Any]:
        return {
            "name": self.env._("Sales Approval Categories"),
            "type": "ir.actions.act_window",
            "res_model": "approval.category",
            "view_mode": "list,form",
            "domain": [
                ("approval_type", "=", "sale"),
                ("company_id", "in", (self.company_id.id, False)),
            ],
            "context": {
                "default_approval_type": "sale",
                "approval_category_routes_by_steps": True,
                "default_company_id": self.company_id.id,
            },
        }
