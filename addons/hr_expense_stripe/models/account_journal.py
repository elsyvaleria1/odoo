from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.hr_expense_stripe.utils import send_request_stripe_proxy


class AccountJournal(models.Model):
    _inherit = "account.journal"

    stripe_currency_id = fields.Many2one(related="company_id.stripe_currency_id")
    stripe_issuing_balance = fields.Monetary(
        string="Stripe Balance Available",
        currency_field="currency_id",
        readonly=True,
    )
    stripe_issuing_balance_timestamp = fields.Integer(
        string="Timestamp of the most recent Stripe Issuing Balance update"
    )
    stripe_card_ids = fields.One2many(
        comodel_name="hr.expense.stripe.card",
        inverse_name="journal_id",
        string="Stripe Cards",
        help="Stripe cards associated with this journal. "
        "They can be used to pay for expenses, or to top up the Stripe Issuing balance.",
    )
    nb_stripe_card = fields.Count(
        count_of="stripe_card_ids",
        compute_sudo=True,
    )

    def _selection_bank_statements_source(self):
        rslt = super()._selection_bank_statements_source()
        rslt.append(("stripe_issuing", self.env._("Stripe Issuing")))
        return rslt

    def _update_bank_cash_dashboard_data(self, dashboard_data) -> None:
        super()._update_bank_cash_dashboard_data(dashboard_data)
        prefetch_ids = tuple(dashboard_data.keys())
        company_stripe_journal_ids = set(self.env.companies.stripe_journal_id.ids)
        for journal_id, journal_data in dashboard_data.items():
            if journal_id in company_stripe_journal_ids:
                journal = self.browse(journal_id).with_prefetch(prefetch_ids)
                journal_data.update(
                    {
                        "stripe_issuing_activated": journal.company_id.stripe_issuing_activated,
                        "stripe_issuing_balance": journal.stripe_currency_id.format(
                            journal.stripe_issuing_balance
                        ),
                    }
                )

    def action_view_stripe_issuing_cards(self):
        return self.stripe_card_ids._get_records_action()

    def action_view_topup_wizard(self) -> dict:
        self.check_singleton()
        self.env["wizard.account.journal.topup"].check_access("create")

        if "EU" in (self.company_id.country_id.country_group_codes or []):
            stripe_country = "eu"
        elif self.company_id.country_id.code == "US":
            stripe_country = "us"
        elif self.company_id.country_id.code == "GB":
            stripe_country = "gb"
        else:
            raise UserError(
                self.env._("Stripe Issuing is not available in your country.")
            )

        if stripe_country == "us":
            usd = self.env.ref("base.USD")
            if not usd.active:
                usd.active = True
            wizard = self.env["wizard.account.journal.topup"].create(
                [
                    {
                        "company_id": self.company_id.id,
                        "currency_id": usd.id,
                        "is_live_mode": self.company_id._get_stripe_mode() == "live",
                    }
                ]
            )
        else:
            company_sudo = self.company_id.sudo()
            payload = {
                "account": company_sudo.stripe_id,
                "bank_transfer": {"type": f"{stripe_country}_bank_transfer"},
                "currency": self.company_id.stripe_currency_id.name,
                "funding_type": "bank_transfer",
            }
            response = send_request_stripe_proxy(
                company_sudo,
                route="funding_instructions",
                payload=payload,
                method="POST",
            )
            wizard = (
                self.env["wizard.account.journal.topup"]
                .with_company(self.company_id)
                ._create_from_funding_instructions(response)
            )

        return {
            "name": self.env._("Top-up"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.account.journal.topup",
            "res_id": wizard.id,
            "target": "new",
        }
