from odoo import fields, models
from odoo.fields import Domain
from odoo.tools import SQL


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_to_pay_select(self):
        """Build the SQL fragment gating which documents count as to-pay."""
        # OVERRIDE
        # The gate applies to the documents this module judges, and to nothing
        # else. Customer invoices used to pass it by collision rather than by
        # rule: a line with no purchase order computes 'exception', and
        # 'exception' happens to be inside this IN list. Now that the compute
        # leaves them unset, the exemption has to be stated.
        #
        # Refunds are exempt on purpose: release-to-pay answers "may we pay this
        # bill", and a credit note is not paid, it offsets. Gating them here
        # would stop them netting off the amount still owed.
        # _release_to_pay_refund_types(), not a second copy of its literal. Its
        # docstring already names this gate as one of the three places that must
        # agree about which judged documents are refunds -- and it was the one
        # place that did not ask, so widening the judged set would have left it
        # behind exactly as that docstring warns.
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
        """Build the search query for the dashboard's draft sales/purchases."""
        # OVERRIDE
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
            # context_today, not today(): core computes the `late` flag of this
            # very dashboard call with fields.Date.context_today, and two
            # expressions of "today" in one render -- one UTC, one in the
            # user's timezone -- make a bill due today appear or vanish
            # depending on the server offset.
            ("invoice_date_due", "<", fields.Date.context_today(self)),
            ("release_to_pay", "=", "yes"),
        ]
        domain = Domain.AND(
            [
                self.env["account.move"]._check_company_domain(self.env.companies),
                Domain("state", "=", "draft"),
                Domain("payment_state", "in", ("not_paid", "partial")),
                Domain.OR([domain_sale, domain_purchase]),
            ]
        )
        return self.env["account.move"]._search(domain, bypass_access=True)
