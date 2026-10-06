from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _get_custody_status(self, company) -> dict:
        self.check_singleton()
        today = fields.Date.context_today(self)
        held = (
            self.env["account.payment"]
            .with_privilege(
                "account_collection.privilege_read_custody_status",
                reason="a collector's custody decides what they may do next",
            )
            .search(
                [
                    ("collector_id", "=", self.id),
                    ("company_id", "=", company.id),
                    ("is_in_custody", "=", True),
                ]
            )
        )
        limit = company.account_config_id.collection_custody_limit
        amount = sum(held.mapped("amount_company_currency_signed"))
        overdue = held.filtered(
            lambda payment: (
                payment.date_custody_due
                and payment.date_custody_due < today
                and payment.collection_remittance_id.state != "submitted"
            )
        )
        return {
            "amount": amount,
            "count": len(held),
            "overdue_amount": sum(overdue.mapped("amount_company_currency_signed")),
            "overdue_count": len(overdue),
            "over_limit": bool(limit)
            and company.currency_id.compare_amounts(amount, limit) >= 0,
            "limit": limit,
        }
