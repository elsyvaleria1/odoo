import base64
import hashlib
import hmac
from wsgiref.handlers import format_date_time

from odoo import fields, models
from odoo.fields import Datetime

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_worldline import const

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "worldline_api_key": "worldline_api_key",
        "worldline_api_secret": "worldline_api_secret",
        "worldline_webhook_key": "worldline_webhook_key",
        "worldline_webhook_secret": "worldline_webhook_secret",
    }

    code = fields.Selection(
        selection_add=[("worldline", "Worldline")],
        ondelete={"worldline": "set default"},
    )
    worldline_pspid = fields.Char(
        string="Worldline PSPID",
        copy=False,
        required_if_provider="worldline",
    )
    worldline_api_key = fields.Char(
        string="Worldline API Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        required_if_provider="worldline",
    )
    worldline_api_secret = fields.Char(
        string="Worldline API Secret",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="worldline",
        groups="base.group_system",
    )
    worldline_webhook_key = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        required_if_provider="worldline",
    )
    worldline_webhook_secret = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="worldline",
        groups="base.group_system",
    )


    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "worldline").update(
            {
                "support_tokenization": True,
            }
        )


    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "worldline":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES


    def _prepare_request_url(self, endpoint, **kwargs):
        if self.code != "worldline":
            return super()._prepare_request_url(endpoint, **kwargs)
        api_url = self._worldline_get_api_url()
        return f"{api_url}/v2/{self.worldline_pspid}/{endpoint}"

    def _worldline_get_api_url(self) -> str:
        if self.state == "enabled":
            return "https://payment.direct.worldline-solutions.com"
        else:
            return "https://payment.preprod.direct.worldline-solutions.com"

    def _prepare_request_headers(
        self, method, endpoint, *args, idempotency_key=None, **kwargs
    ):
        if self.code != "worldline":
            return super()._prepare_request_headers(
                method, endpoint, *args, idempotency_key=idempotency_key, **kwargs
            )

        content_type = "application/json; charset=utf-8" if method == "POST" else ""
        dt = format_date_time(
            Datetime.now().timestamp()
        )
        signature = self._get_worldline_signature(
            method, endpoint, content_type, dt, idempotency_key=idempotency_key
        )
        authorization_header = f"GCS v1HMAC:{self.worldline_api_key}:{signature}"
        headers = {
            "Authorization": authorization_header,
            "Date": dt,
            "Content-Type": content_type,
        }
        if method == "POST" and idempotency_key:
            headers["X-GCS-Idempotence-Key"] = idempotency_key
        return headers

    def _get_worldline_signature(
        self, method, endpoint, content_type, dt_rfc, idempotency_key=None
    ):
        values_to_sign = [method, content_type, dt_rfc]
        if idempotency_key:
            values_to_sign.append(f"x-gcs-idempotence-key:{idempotency_key}")
        values_to_sign.append(f"/v2/{self.worldline_pspid}/{endpoint}")

        signing_str = "\n".join(values_to_sign) + "\n"
        signature = hmac.new(
            self.worldline_api_secret.encode(), signing_str.encode(), hashlib.sha256
        )
        return base64.b64encode(signature.digest()).decode("utf-8")

    def _parse_response_error(self, response):
        if self.code != "worldline":
            return super()._parse_response_error(response)
        return ", ".join(
            [error.get("message", "") for error in response.json().get("errors", [])]
        )
