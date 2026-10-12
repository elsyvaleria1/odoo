from urllib.parse import urlencode

from odoo import api, fields, models

from odoo.addons.payment import utils as payment_utils


class WizardPaymentTransactionViewLink(models.TransientModel):
    _name = "wizard.payment.transaction.view.link"
    _description = "Generate Payment Link"

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res_id = self.env.context.get("active_id")
        res_model = self.env.context.get("active_model")
        if res_id and res_model:
            res.update({"res_model": res_model, "res_id": res_id})
            res.update(self.env[res_model].browse(res_id)._prepare_payment_link_vals())
        return res

    res_model = fields.Char(
        string="Related Document Model",
        required=True,
    )
    res_id = fields.Integer(
        string="Related Document ID",
        required=True,
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        required=True,
    )
    amount_max = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(comodel_name="res.currency")
    partner_id = fields.Many2one(comodel_name="res.partner")
    partner_email = fields.Char(related="partner_id.email")
    link = fields.Char(
        string="Payment Link",
        compute="_compute_link",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
    )
    warning_message = fields.Char(compute="_compute_warning_message")

    @api.depends("amount", "amount_max")
    def _compute_warning_message(self) -> None:
        self.warning_message = ""
        for wizard in self:
            if wizard.amount_max <= 0:
                wizard.warning_message = self.env._("There is nothing to be paid.")
            elif wizard.amount <= 0:
                wizard.warning_message = self.env._("Please set a positive amount.")
            elif wizard.amount > wizard.amount_max:
                wizard.warning_message = self.env._(
                    "Please set an amount lower than %s.",
                    wizard.currency_id.format(wizard.amount_max),
                )

    @api.depends("res_model", "res_id")
    def _compute_company_id(self):
        for link in self:
            record = self.env[link.res_model].browse(link.res_id)
            link.company_id = record.company_id if "company_id" in record else False

    @api.depends("amount", "currency_id", "partner_id", "company_id")
    def _compute_link(self) -> None:
        for payment_link in self:
            related_document = self.env[payment_link.res_model].browse(
                payment_link.res_id
            )
            base_url = related_document.get_base_url()
            url = self._prepare_url(base_url, related_document)
            query_params = self._prepare_query_params(related_document)
            anchor = self._prepare_anchor()
            if "?" in url:
                payment_link.link = f"{url}&{urlencode(query_params)}{anchor}"
            else:
                payment_link.link = f"{url}?{urlencode(query_params)}{anchor}"

    def _prepare_url(self, base_url, related_document):
        return f"{base_url}/payment/pay"

    def _prepare_query_params(self, related_document):
        self.check_singleton()
        return {
            "amount": self.amount,
            "access_token": self._prepare_access_token(),
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
        }

    def _prepare_access_token(self):
        self.check_singleton()
        return payment_utils.generate_access_token(
            self.partner_id.id,
            self.amount,
            self.currency_id.id,
            env=self.env,
        )

    def _prepare_anchor(self):
        self.check_singleton()
        return ""
