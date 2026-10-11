from odoo import api, fields, models
from odoo.tools import format_date, formatLang, str2bool

from odoo.addons.payment import utils as payment_utils


class WizardPaymentTransactionViewLink(models.TransientModel):
    _inherit = "wizard.payment.transaction.view.link"

    invoice_amount_due = fields.Monetary(
        string="Amount Due",
        currency_field="currency_id",
        compute="_compute_invoice_amount_due",
    )
    open_installments = fields.Json(export_string_translation=False)
    open_installments_preview = fields.Html(
        export_string_translation=False,
        compute="_compute_open_installments_preview",
    )
    display_open_installments = fields.Boolean(
        compute="_compute_display_open_installments"
    )
    has_eligible_epd = fields.Boolean()
    discount_date = fields.Date()
    epd_info = fields.Char(
        string="Early Payment Discount Information",
        compute="_compute_epd_info",
    )

    def _compute_warning_message(self) -> None:
        super()._compute_warning_message()
        for wizard in self:
            if not wizard.warning_message and not str2bool(
                self.env.registry.settings.get(
                    self.env, "account_payment_provider.enable_portal_payment", False
                )
            ):
                wizard.warning_message = self.env._(
                    "Online payment option is not enabled in Configuration."
                )

    @api.depends("amount_max")
    def _compute_invoice_amount_due(self) -> None:
        for wizard in self:
            wizard.invoice_amount_due = wizard.amount_max

    @api.depends("open_installments")
    def _compute_open_installments_preview(self) -> None:
        for wizard in self:
            preview = ""
            if wizard.display_open_installments:
                for installment in wizard.open_installments or []:
                    preview += "<div>"
                    preview += self.env._(
                        '#%(number)s - Installment of <strong>%(amount)s</strong> due on <strong class="text-primary">%(date)s</strong>',
                        number=installment["number"],
                        amount=formatLang(
                            self.env,
                            installment["amount"],
                            currency_obj=wizard.currency_id,
                        ),
                        date=installment["date_maturity"],
                    )
                    preview += "</div>"
            wizard.open_installments_preview = preview

    @api.depends("amount")
    def _compute_epd_info(self) -> None:
        for wizard in self:
            wizard.epd_info = ""
            if wizard.has_eligible_epd and not wizard.currency_id.compare_amounts(
                wizard.amount, wizard.invoice_amount_due
            ):
                msg = self.env._(
                    "A discount will be applied if the customer pays before %s included.",
                    format_date(wizard.env, wizard.discount_date),
                )
                wizard.epd_info = msg

    @api.depends("open_installments")
    def _compute_display_open_installments(self) -> None:
        for wizard in self:
            installments = wizard.open_installments or []
            wizard.display_open_installments = len(installments) > 1

    def _prepare_url(self, base_url, related_document):
        res = super()._prepare_url(base_url, related_document)
        if self.res_model != "account.move":
            return res

        return f"{base_url}/{related_document.get_portal_url()}"

    def _prepare_query_params(self, related_document):
        res = super()._prepare_query_params(related_document)
        if self.res_model != "account.move":
            return res

        return {
            "amount": self.amount,
            "payment_token": self._prepare_access_token(),
            "payment": True,
        }

    def _prepare_access_token(self):
        res = super()._prepare_access_token()
        if self.res_model != "account.move":
            return res

        return payment_utils.generate_access_token(
            self.res_id, self.amount, env=self.env
        )

    def _prepare_anchor(self):
        res = super()._prepare_anchor()
        if self.res_model != "account.move":
            return res

        return "#portal_pay"
