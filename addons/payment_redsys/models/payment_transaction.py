import base64

from odoo import api, fields, models
from odoo.http import request
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.tools import consteq
from odoo.tools.urls import urljoin

from odoo.addons.integration.tools.admission import Acknowledged
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import COUNTRY_NUMERIC_CODES
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_redsys import const
from odoo.addons.payment_redsys.controllers.main import RedsysController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _decode_redsys_notification(self, encoded_data):
        encoded = encoded_data.get("Ds_MerchantParameters")
        if not encoded:
            return None
        try:
            data = json_loads(base64.b64decode(encoded).decode())
        except ValueError, TypeError:
            return None
        return data if isinstance(data, dict) else None

    @api.model
    def _receiver_for_redsys_notification(self, acknowledged) -> tuple:
        encoded_data = request.get_http_params()
        data = self._decode_redsys_notification(encoded_data)
        if data is None:
            raise acknowledged
        tx, extra = self._resolve_notification("redsys", data, acknowledged)
        return tx, {**extra, "encoded_data": encoded_data}

    @api.model
    def _receiver_for_redsys_return(self, **path_args):
        return self._receiver_for_redsys_notification(
            Acknowledged.redirect("/payment/status")
        )

    @api.model
    def _receiver_for_redsys_webhook(self, **path_args):
        return self._receiver_for_redsys_notification(Acknowledged(""))

    def _is_notification_signature_valid(self, payment_data) -> bool:
        if self.provider_code != "redsys":
            return super()._is_notification_signature_valid(payment_data)
        received_signature = payment_data.get("Ds_Signature")
        if not received_signature:
            _logger.warning("Received notification with missing signature.")
            return False
        expected_signature = self.provider_id._get_redsys_signature(
            payment_data.get("Ds_MerchantParameters"),
            self.reference,
            self.provider_id.redsys_secret_key,
        )
        if not consteq(received_signature, expected_signature):
            _logger.warning("Received notification with invalid signature.")
            return False
        return True

    @api.model_create_multi
    def create(self, vals_list):
        transactions = super().create(vals_list)
        for tx in transactions.filtered(lambda t: t.provider_code == "redsys"):
            tx.provider_reference = tx.reference
        return transactions

    def _get_unique_reference(
        self,
        provider_code,
        prefix=None,
        separator="-",
        references_in_use: set[str] | None = None,
        **kwargs,
    ) -> str:
        if provider_code != "redsys":
            return super()._get_unique_reference(
                provider_code,
                prefix=prefix,
                separator=separator,
                references_in_use=references_in_use,
                **kwargs,
            )

        prefix = str(int(fields.Datetime.now().timestamp()))[-10:]

        return super()._get_unique_reference(
            provider_code,
            prefix=prefix,
            separator="S",
            references_in_use=references_in_use,
            **kwargs,
        )

    def _prepare_redirect_form_values(self, processing_values):
        if self.provider_code != "redsys":
            return super()._prepare_redirect_form_values(processing_values)

        merchant_parameters = self._redsys_prepare_merchant_parameters()
        encoded_merchant_parameters = base64.b64encode(
            json_dumps_bytes(merchant_parameters)
        ).decode()
        signature = self.provider_id._get_redsys_signature(
            encoded_merchant_parameters,
            self.reference,
            self.provider_id.redsys_secret_key,
        )
        return {
            "api_url": self.provider_id._redsys_get_api_url(),
            "merchant_parameters": encoded_merchant_parameters,
            "signature": signature,
            "signature_version": "HMAC_SHA256_V1",
        }

    def _redsys_prepare_merchant_parameters(self) -> dict:
        converted_amount = payment_utils.major_to_minor_currency_units(
            self.amount, self.currency_id
        )
        base_url = self.provider_id.get_base_url()
        return_url = urljoin(base_url, RedsysController._return_url)
        webhook_url = urljoin(base_url, RedsysController._webhook_url)
        return {
            "DS_MERCHANT_AMOUNT": str(converted_amount),
            "DS_MERCHANT_CURRENCY": self.currency_id.iso_numeric,
            "DS_MERCHANT_MERCHANTCODE": self.provider_id.redsys_merchant_code,
            "DS_MERCHANT_TERMINAL": self.provider_id.redsys_merchant_terminal,
            "DS_MERCHANT_ORDER": self.reference,
            "DS_MERCHANT_MERCHANTURL": webhook_url,
            "DS_MERCHANT_TRANSACTIONTYPE": "0",
            "DS_MERCHANT_URLOK": return_url,
            "DS_MERCHANT_URLKO": return_url,
            "DS_MERCHANT_PAYMETHODS": const.PAYMENT_METHODS_MAPPING.get(
                self.payment_method_id.code, "C"
            ),
            "DS_MERCHANT_EMV3DS": {
                "billAddrCity": self.partner_city,
                "billAddrCountry": COUNTRY_NUMERIC_CODES.get(
                    self.partner_country_id.code, ""
                ),
                "billAddrLine1": self.partner_address,
                "billAddrPostCode": self.partner_zip,
                "billAddrState": self.partner_state_id.code,
                "cardholderName": self.partner_name,
                "email": self.partner_email,
            },
        }

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != "redsys":
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get("Ds_Order")

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "redsys":
            return super()._extract_amount_data(payment_data)

        amount = payment_utils.minor_to_major_currency_units(
            float(payment_data.get("Ds_Amount", 0)), self.currency_id
        )
        currency = (
            self.env["res.currency"]
            .search([("iso_numeric", "=", payment_data.get("Ds_Currency"))], limit=1)
            .name
        )
        return {
            "amount": amount,
            "currency_code": currency,
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "redsys":
            return super()._apply_updates(payment_data)

        card_brand = payment_data.get("Ds_Card_Brand")
        payment_method = self.env["payment.method"]._get_from_code(
            card_brand, mapping=const.PAYMENT_METHODS_MAPPING
        )
        self.payment_method_id = payment_method or self.payment_method_id

        status_code = payment_data["Ds_Response"]
        if status_code in const.PAYMENT_STATUS_MAPPING["done"]:
            self._set_done()
        elif status_code in const.PAYMENT_STATUS_MAPPING["cancel"]:
            self._set_canceled()
        elif status_code in const.PAYMENT_STATUS_MAPPING["error"]:
            self._set_error(
                self.env._(
                    "An error occurred during the processing of your payment (%s). Please try again.",
                    payment_data.get("Ds_ErrorCode"),
                )
            )
        else:
            _logger.warning("Received invalid payment status (%s).", status_code)
            self._set_error(self.env._("Unknown status code: %s", status_code))
        return None
