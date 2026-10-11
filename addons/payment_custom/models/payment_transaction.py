from odoo import api, models
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_custom.controllers.main import CustomController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _receiver_for_custom_process(self, **path_args) -> tuple:
        post = request.get_http_params()
        tx = self.sudo()._search_by_reference("custom", post)
        return tx, {"post": post}

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.provider_code != "custom":
            return super()._is_inbound_request_authentic(headers, body)
        post = request.get_http_params() if request else {}
        if not payment_utils.is_access_token_valid(
            post.get("access_token"), self.reference, self.amount
        ):
            _logger.warning(
                "Refused custom processing of %s: invalid access token.", self.reference
            )
            return False
        return True

    def _prepare_redirect_form_values(self, processing_values):
        if self.provider_code != "custom":
            return super()._prepare_redirect_form_values(processing_values)

        return {
            "api_url": CustomController._process_url,
            "reference": self.reference,
            "access_token": payment_utils.generate_access_token(
                self.reference, self.amount, env=self.env
            ),
        }

    def _get_communication(self):
        self.check_singleton()
        communication = ""
        if hasattr(self, "invoice_ids") and self.invoice_ids:
            communication = self.invoice_ids[0].payment_reference
        elif hasattr(self, "sale_order_ids") and self.sale_order_ids:
            communication = self.sale_order_ids[0].reference
        return communication or self.reference

    def _get_custom_qr_code(self):
        self.check_singleton()
        if not self.provider_id.sudo().qr_code:
            return None
        bank = self.company_id.sudo().partner_id.bank_account_ids[:1]
        if not bank or not hasattr(bank, "prepare_qr_code_base64"):
            return None
        return bank.prepare_qr_code_base64(
            self.amount,
            self._get_communication(),
            None,
            self.currency_id,
            self.partner_id,
        )

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "custom":
            return super()._extract_amount_data(payment_data)
        return None

    def _apply_updates(self, payment_data):
        if self.provider_code != "custom":
            return super()._apply_updates(payment_data)

        _logger.info(
            "Validated custom payment for transaction %s: set as pending.",
            self.reference,
        )
        self._set_pending()
        return None

    def _log_received_message(self) -> None:
        other_provider_txs = self.filtered(lambda t: t.provider_code != "custom")
        super(PaymentTransaction, other_provider_txs)._log_received_message()

    def _get_sent_message(self):
        message = super()._get_sent_message()
        if self.provider_code == "custom":
            message = self.env._(
                "The customer has selected %(provider_name)s to make the payment.",
                provider_name=self.provider_id.name,
            )
        return message
