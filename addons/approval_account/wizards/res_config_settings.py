from typing import Any

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    invoice_approval_threshold = fields.Monetary(
        related="company_id.invoice_approval_threshold",
        currency_field="company_currency_id",
        readonly=False,
    )
    bill_approval_threshold = fields.Monetary(
        related="company_id.bill_approval_threshold",
        currency_field="company_currency_id",
        readonly=False,
    )
    auto_post_on_approval = fields.Boolean(
        related="company_id.auto_post_on_approval",
        readonly=False,
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Company Currency",
        readonly=True,
    )

    def action_view_pending_invoice_approvals(self) -> dict[str, Any]:
        return {
            "name": self.env._("Pending Invoice/Bill Approvals"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("approval_state", "=", "pending"),
                (
                    "move_type",
                    "in",
                    ["out_invoice", "in_invoice", "out_refund", "in_refund"],
                ),
            ],
            "context": {"create": False},
        }

    def action_view_invoice_approval_categories(self) -> dict[str, Any]:
        # The window action behind Accounting -> Configuration -> Approval
        # Types, rather than a second one: a hand-rolled domain here answered
        # "which categories are the accounting ones" differently from the menu
        # and from the runtime lookup, dropping global categories and the
        # payment type, and its default_company_id made every category created
        # from this button company-specific.
        return self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "approval_account.action_approval_category_accounting",
        )
