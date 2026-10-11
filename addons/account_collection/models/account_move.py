from odoo import Command, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _prepare_collected_invoice(self, collection_method) -> None:
        pass

    def _issue_collected_invoice(self) -> None:
        pass

    def _get_collection_journal(self):
        company = self.company_id[:1] or self.env.company
        return self.env["account.journal"].search(
            [
                *self.env["account.journal"]._check_company_domain(company),
                ("is_collection_custody", "=", True),
            ],
            limit=1,
        )

    def _create_collection_payment(
        self,
        amount,
        date,
        collection_method,
        collector,
        journal=None,
        memo=None,
        check_date=None,
    ):
        receivables = self.line_ids.filtered(
            lambda line: (
                line.account_type == "asset_receivable"
                and not line.reconciled
                and line.parent_state == "posted"
            )
        )
        invoices = receivables.move_id
        if not invoices or invoices.filtered(
            lambda move: move.move_type not in ("out_invoice", "out_receipt")
        ):
            raise UserError(
                self.env._("Only open, posted customer invoices can be collected.")
            )
        if len(invoices.commercial_partner_id) > 1:
            raise UserError(
                self.env._("One collection settles the invoices of one customer.")
            )
        if invoices.currency_id != invoices.company_id.currency_id:
            raise UserError(
                self.env._(
                    "A collection in custody is recorded in %(currency)s; collect "
                    "invoices in another currency at the office.",
                    currency=invoices.company_id.currency_id.name,
                )
            )
        journal = journal or invoices._get_collection_journal()
        if not journal:
            raise UserError(
                self.env._(
                    "%(company)s has no collection custody journal.",
                    company=invoices.company_id.name,
                )
            )
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": invoices.commercial_partner_id.id,
                "company_id": invoices.company_id.id,
                "journal_id": journal.id,
                "currency_id": invoices.company_id.currency_id.id,
                "amount": amount,
                "date": date,
                "memo": memo or ", ".join(invoices.mapped("name")),
                "counterpart_account_id": receivables.account_id[:1].id,
                "collector_id": collector.id,
                "collection_method": collection_method,
                "collection_check_date": check_date
                if collection_method == "check"
                else False,
            }
        )
        payment.action_post()
        counterpart = payment.move_id.line_ids.filtered(
            lambda line: (
                line.account_id in receivables.account_id and not line.reconciled
            )
        )
        (counterpart + receivables).reconcile()
        invoices.matched_payment_ids = [Command.link(payment.id)]
        payment._send_collection_receipt()
        return payment
