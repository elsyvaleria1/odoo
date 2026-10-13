from odoo import fields, models
from odoo.fields import Domain
from odoo.tools import SQL


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_to_pay_select(self):
        AccountMove = self.env["account.move"]
        refund_types = AccountMove._release_to_pay_refund_types()
        gated_types = [
            move_type
            for move_type in AccountMove._release_to_pay_move_types()
            if move_type not in refund_types
        ]
        return SQL(
            "(move_type != ALL(%s) OR release_to_pay IN ('yes', 'exception')) AS to_pay",
            gated_types,
        )

    def _get_draft_sales_purchases_query(self):
        domain_sale = [
            ("journal_id", "in", self.filtered(lambda j: j.type == "sale").ids),
            (
                "move_type",
                "in",
                self.env["account.move"].get_sale_types(include_receipts=True),
            ),
        ]

        domain_purchase = [
            ("journal_id", "in", self.filtered(lambda j: j.type == "purchase").ids),
            (
                "move_type",
                "in",
                self.env["account.move"]._release_to_pay_move_types(),
            ),
            "|",
            ("invoice_date_due", "<", fields.Date.context_today(self)),
            ("release_to_pay", "=", "yes"),
        ]
        domain = Domain.AND(
            [
                self.env["account.move"]._get_domain_company_compatible(
                    self.env.companies
                ),
                Domain("state", "=", "draft"),
                Domain("payment_state", "in", ("not_paid", "partial")),
                Domain.OR([domain_sale, domain_purchase]),
            ]
        )
        return self.env["account.move"]._search(domain, bypass_access=True)
