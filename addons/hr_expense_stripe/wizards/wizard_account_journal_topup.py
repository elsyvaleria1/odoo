from typing import Self

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.hr_expense_stripe.utils import (
    format_amount_to_stripe,
    send_request_stripe_proxy,
)


class WizardAccountJournalTopup(models.TransientModel):
    _name = "wizard.account.journal.topup"
    _description = "Stripe Issuing Top-up Wizard"
    _check_company_auto = True

    pull_push_funds = fields.Selection(
        selection=[
            ("push", "Push Funds to a Funding Instruction"),
            ("pull", "Directly pull funds from the company bank account"),
        ],
        compute="_compute_pull_push_funds",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
        required=True,
    )
    bank_account_id = fields.Many2one(
        comodel_name="res.partner.bank.account",
        string="IBAN",
        readonly=True,
    )
    account_number = fields.Char(
        related="bank_account_id.acc_number",
        string="Account number",
        readonly=True,
    )
    bic = fields.Char(
        related="bank_account_id.bank_bic",
        string="BIC",
        readonly=True,
    )
    qr_code = fields.Html(
        string="QR Code URL",
        compute="_compute_qr_code",
    )
    is_live_mode = fields.Boolean(
        string="Live Mode",
        default=True,
        readonly=True,
        required=True,
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        default=1000.0,
    )
    statement_description = fields.Char(
        string="Bank statement description",
        size=15,
        default=lambda self: self.env._("Stripe Top-Up"),
    )

    @api.constrains("statement_description")
    def _check_statement_is_only_ascii(self) -> None:
        for wizard in self:
            if not wizard.statement_description:
                continue
            try:
                wizard.statement_description.encode("ascii")
            except UnicodeEncodeError:
                raise ValidationError(
                    self.env._(
                        "The statement description can only contain 15 ASCII characters"
                    )
                ) from None

    @api.depends("company_id")
    def _compute_pull_push_funds(self) -> None:
        for wizard in self:
            wizard.pull_push_funds = (
                "pull" if wizard.company_id.country_code == "US" else "push"
            )

    @api.model
    def _create_from_funding_instructions(self, fi_object) -> Self:
        """Set up the displayed data according to the `funding_instruction` object sent by Stripe
        This also creates a partner and banking information for Stripe so it can be reused
        """
        currency = self.env["res.currency"].search(
            [("name", "ilike", fi_object["currency"])], limit=1
        )
        if not currency:
            raise UserError(
                self.env._(
                    "Currency %(name)s is not available in the system. Please activate it",
                    name=fi_object["currency"],
                )
            )

        financial_address = None
        supported_networks = []

        for address in fi_object["bank_transfer"]["financial_addresses"]:
            financial_address = address[address["type"]]
            supported_networks = address["supported_networks"]
            break

        if not financial_address:
            raise UserError(
                self.env._(
                    "Only IBAN is supported for Stripe Issuing funding instructions right now"
                )
            )

        if "sepa" not in supported_networks:
            raise UserError(
                self.env._(
                    "Only SEPA is supported for Stripe Issuing funding instructions right now"
                )
            )

        # Search or create the partner
        partner_bank = self.env["res.partner.bank.account"].search(
            domain=[("acc_number", "=", financial_address["iban"])],
            limit=1,
        )

        if not partner_bank:
            partner_country = self.env["res.country"].search(
                [("code", "ilike", financial_address["country"])], limit=1
            )
            account_holder_address = financial_address["account_holder_address"]
            state = self.env["res.country.state"].search(
                [("name", "ilike", account_holder_address["state"])], limit=1
            )
            partner = self.env["res.partner"].create(
                [
                    {
                        "name": financial_address["account_holder_name"],
                        "country_id": partner_country and partner_country.id,
                        "state_id": state and state.id,
                        "is_company": True,
                        "city": account_holder_address["city"],
                        "street": account_holder_address["line1"],
                        "street2": account_holder_address["line2"],
                        "zip": account_holder_address["postal_code"],
                        "website": "https://www.stripe.com",
                    }
                ]
            )

            bank = self.env["res.bank"].search(
                [("bic", "ilike", financial_address["bic"])], limit=1
            )
            if not bank:
                bank_address = financial_address["bank_address"]
                bank_country = self.env["res.country"].search(
                    [("code", "ilike", bank_address["country"])], limit=1
                )
                bank_state = self.env["res.country.state"].search(
                    [("name", "ilike", bank_address["state"])], limit=1
                )
                bank = self.env["res.bank"].create(
                    [
                        {
                            "name": self.env._("Stripe Partner Bank"),
                            "bic": financial_address["bic"],
                            "country": bank_country and bank_country.id,
                            "state": bank_state and bank_state.id,
                            "city": bank_address["city"],
                            "street": bank_address["line1"],
                            "street2": bank_address["line2"],
                            "zip": bank_address["postal_code"],
                        }
                    ]
                )

            partner_bank = self.env["res.partner.bank.account"].create(
                [
                    {
                        "acc_number": financial_address["iban"],
                        "currency_id": currency.id,
                        "partner_id": partner.id,
                        "bank_id": bank.id,
                        "allow_out_payment": True,
                    }
                ]
            )

        return self.create(
            [
                {
                    "company_id": self.env.company.id,
                    "currency_id": currency.id,
                    "is_live_mode": fi_object["livemode"],
                    "pull_push_funds": "push",
                    "bank_account_id": partner_bank.id,
                }
            ]
        )

    @api.depends("bank_account_id", "amount", "currency_id")
    def _compute_qr_code(self) -> None:
        for wizard in self:
            bank = wizard.bank_account_id
            if wizard.pull_push_funds == "pull" or not (
                bank and bank.allow_out_payment and wizard.amount and wizard.currency_id
            ):
                wizard.qr_code = False
                continue

            b64_qr = bank.prepare_qr_code_base64(
                amount=wizard.amount,
                free_communication=self.env._("Top up payment"),
                structured_communication=False,
                currency=wizard.currency_id,
                debtor_partner=bank.partner_id,
            )
            if b64_qr:
                wizard.qr_code = Markup(
                    '<img class="border border-dark rounded" src="{b64_qr}"/>'
                    "<br/><strong>{caption}</strong>"
                ).format(
                    b64_qr=b64_qr,
                    caption=self.env._("Scan me with your banking app."),
                )
            else:
                wizard.qr_code = False

    def action_topup(self) -> None:
        """US only, send the topup request to stripe so we can test payments without going to stripe dashboard"""
        self.check_singleton()
        if self.pull_push_funds == "push" or self.company_id.country_code != "US":
            raise UserError(
                self.env._("The direct top-up isn't available outside of the US.")
            )

        payload = {
            "account": self.sudo().company_id.stripe_id,
            "amount": format_amount_to_stripe(self.amount, self.currency_id),
            "currency": self.currency_id.name,
            "statement_descriptor": self.statement_description,
        }

        response = send_request_stripe_proxy(
            self.company_id.sudo(), route="topups", payload=payload, method="POST"
        )
        match response["status"]:
            case "pending" | "succeeded":
                self.env.user._bus_send(
                    "simple_notification",
                    {
                        "type": "success",
                        "message": self.env._(
                            "Top-up request successfully sent to Stripe, this can take a few days before being available"
                        ),
                    },
                )
            case "failed":
                msg = response.get("description", self.env._("Unknown"))
                self.env.user._bus_send(
                    "simple_notification",
                    {
                        "type": "danger",
                        "message": self.env._(
                            "Top-up request failed with the following error sent by Stripe:\n%(stripe_error)s",
                            stripe_error=msg,
                        ),
                    },
                )  # What if it fails? What if we want to cancel it (US-case TBDL) ?
