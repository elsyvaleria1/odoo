import logging
import re
from urllib.parse import parse_qs, urlsplit

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from odoo.tools import hash_sign, register_signed_scope, resolve_hash_signed

from odoo.addons.integration.tools.admission import Acknowledged
from odoo.addons.payment_mollie import const

_logger = logging.getLogger(__name__)
WEBHOOK_SCOPE = register_signed_scope(
    "pos_mollie",
    purpose="the Mollie webhook reports the payment of the POS session and "
    "payment method the token names",
    lifetime="dated: 27 hours, Mollie's retry window",
)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    @api.model
    def _receiver_for_mollie_terminal(self, **path_args) -> tuple:
        payload = request.get_http_params().get("payload") or ""
        decoded_payload = resolve_hash_signed(self.sudo().env, WEBHOOK_SCOPE, payload)
        if not decoded_payload:
            _logger.warning("Invalid payload received in Mollie webhook, ignoring")
            request.env["integration.exchange"]._record_unknown_caller(
                self._name,
                "mollie webhook with an invalid signed payload",
                request.httprequest.remote_addr,
                user_agent=request.httprequest.headers.get("User-Agent"),
                status_code=200,
            )
            raise Acknowledged("OK")
        method = self.sudo().browse(decoded_payload["payment_method_id"]).exists()
        if not method:
            _logger.warning("No payment method found matching Mollie webhook, ignoring")
            raise Acknowledged("OK")
        return method, {"payload": decoded_payload}

    def _inbound_gate_owner(self):
        return self, f"{self.name} notifications", None

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.use_payment_terminal != "mollie":
            return super()._is_inbound_request_authentic(headers, body)
        # The payload is signed by this database (hash_sign) and names the
        # method: resolving it is the verification.
        payload = request.get_http_params().get("payload") or ""
        decoded = resolve_hash_signed(self.sudo().env, WEBHOOK_SCOPE, payload)
        return bool(decoded) and decoded.get("payment_method_id") == self.id

    def _selection_payment_terminals(self):
        return super()._selection_payment_terminals() + [("mollie", "Mollie")]

    mollie_terminal_id = fields.Char(
        string="Mollie Terminal ID",
        copy=False,
    )
    mollie_payment_provider_id = fields.Many2one(
        comodel_name="payment.provider",
        domain=[("code", "=", "mollie")],
    )

    @api.constrains("mollie_payment_provider_id")
    def _check_mollie_payment_provider_id(self) -> None:
        for payment_method in self:
            if not payment_method.mollie_payment_provider_id:
                continue
            if not payment_method.mollie_payment_provider_id.mollie_api_key:
                raise ValidationError(
                    self.env._(
                        "Please set the Mollie API Key field on the %s payment provider.",
                        payment_method.mollie_payment_provider_id.name,
                    )
                )

    def _mollie_check_session(self, pos_session_id) -> None:
        session = (
            self.env["pos.session"].browse(pos_session_id).exists()
            if isinstance(pos_session_id, int)
            else self.env["pos.session"]
        )
        if (
            not session
            or session.state != "opened"
            or self not in session.config_id.payment_method_ids
        ):
            raise AccessError(
                self.env._(
                    "Mollie payments are taken in an open session using %s.",
                    self.display_name,
                )
            )

    def _mollie_own_payment(self, payment_id) -> dict:
        if not isinstance(payment_id, str) or not self._MOLLIE_PAYMENT_ID.fullmatch(
            payment_id
        ):
            raise AccessError(self.env._("Invalid Mollie payment reference."))
        payment_info = self._mollie_get_payment(payment_id)
        if not self._is_own_mollie_payment(payment_info):
            raise AccessError(
                self.env._("This Mollie payment was not requested by this method.")
            )
        return payment_info

    def mollie_create_payment(
        self, amount: float, payment_uuid: str, pos_session_id: int
    ):
        self.check_singleton()
        self._mollie_check_session(pos_session_id)

        user_lang = self.env.context.get("lang")
        currency = self.journal_id.currency_id or self.company_id.currency_id
        payload = {
            "payment_uuid": payment_uuid,
            "payment_method_id": self.id,
            "pos_session_id": pos_session_id,
        }
        signed_payload = hash_sign(
            self.sudo().env, WEBHOOK_SCOPE, payload, expiration_hours=27
        )  # Mollie webhooks can retry for up to 26 hours
        payment_request = {
            "amount": {
                "currency": currency.name,
                "value": f"{amount:.{currency.decimal_places}f}",
            },
            "locale": user_lang if user_lang in const.SUPPORTED_LOCALES else "en_US",
            "description": self._get_mollie_payment_description(
                pos_session_id, payment_uuid
            ),
            "redirectUrl": f"{self.get_base_url()}",  # Not used for POS payments but required by Mollie API
            "webhookUrl": f"{self.get_base_url()}/pos_mollie/webhook?payload={signed_payload}",
            "method": "pointofsale",
            "terminalId": self.mollie_terminal_id,
        }
        return self.mollie_payment_provider_id._send_api_request(
            "POST", "/payments", json=payment_request
        )

    def mollie_create_refund(
        self,
        original_payment_id: str,
        amount: float,
        payment_uuid: str,
        pos_session_id: int,
    ):
        self.check_singleton()
        self._mollie_check_session(pos_session_id)
        self._mollie_own_payment(original_payment_id)

        currency = self.journal_id.currency_id or self.company_id.currency_id
        payment_request = {
            "amount": {
                "currency": currency.name,
                "value": f"{amount:.{currency.decimal_places}f}",
            },
            "description": self._get_mollie_payment_description(
                pos_session_id, payment_uuid
            ),
        }
        return self.mollie_payment_provider_id._send_api_request(
            "POST", f"/payments/{original_payment_id}/refunds", json=payment_request
        )

    def mollie_cancel_payment(self, payment_id: str):
        self.check_singleton()
        self._mollie_own_payment(payment_id)
        return self.mollie_payment_provider_id._send_api_request(
            "DELETE", f"/payments/{payment_id}"
        )

    @api.model
    def _get_mollie_payment_description(self, pos_session_id, payment_uuid) -> str:
        return f"pos_session_id={pos_session_id},payment_uuid={payment_uuid}"

    def _mollie_get_payment(self, payment_id: str):
        self.check_singleton()
        return self.mollie_payment_provider_id._send_api_request(
            "GET", f"/payments/{payment_id}"
        )

    _MOLLIE_PAYMENT_ID = re.compile(r"tr_[A-Za-z0-9]+")

    def mollie_get_payment_status(self, payment_id: str) -> dict:
        self.check_singleton()
        return self._mollie_payment_status(
            payment_id, self._mollie_own_payment(payment_id)
        )

    def _is_own_mollie_payment(self, payment_info) -> bool:
        webhook_url = (
            payment_info.get("webhookUrl") if isinstance(payment_info, dict) else None
        )
        if not isinstance(webhook_url, str):
            return False
        payloads = parse_qs(urlsplit(webhook_url).query).get("payload") or [""]
        decoded = resolve_hash_signed(self.env(su=True), WEBHOOK_SCOPE, payloads[0])
        return isinstance(decoded, dict) and decoded.get("payment_method_id") == self.id

    @api.model
    def _mollie_payment_status(self, payment_id: str, payment_info: dict) -> dict:
        status = {"payment_id": payment_id, "status": payment_info["status"]}
        if status["status"] == "paid":
            payment_details = payment_info.get("details") or {}
            status |= {
                "card_type": payment_details.get("cardFunding"),
                "card_no": payment_details.get("cardNumber"),
                "card_brand": payment_details.get("cardLabel"),
            }
        elif status["status"] in ["expired", "failed", "canceled"]:
            status |= {"status_reason": payment_info.get("statusReason")}
        return status
