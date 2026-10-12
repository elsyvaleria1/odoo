import base64
import hashlib
import hmac

from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes

from odoo import fields, models

from odoo.addons.payment_redsys import const


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "redsys_secret_key": "redsys_secret_key",
    }

    code = fields.Selection(
        selection_add=[("redsys", "Redsys")],
        ondelete={"redsys": "set default"},
    )
    redsys_merchant_code = fields.Char(
        copy=False,
        required_if_provider="redsys",
    )
    redsys_merchant_terminal = fields.Char(
        copy=False,
        required_if_provider="redsys",
    )
    redsys_secret_key = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="redsys",
        groups="base.group_system",
    )

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "redsys":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _redsys_get_api_url(self) -> str:
        if self.state == "enabled":
            return "https://sis.redsys.es/sis/realizarPago"
        else:
            return "https://sis-t.redsys.es:25443/sis/realizarPago"

    def _get_redsys_signature(self, merchant_parameters, reference, secret_key):
        decoded_key = base64.b64decode(secret_key)
        encoded_order = reference.encode().ljust(16, b"\x00")
        cipher = Cipher(TripleDES(decoded_key), modes.CBC(b"\x00" * 8))
        derived_key = (
            cipher.encryptor().update(encoded_order) + cipher.encryptor().finalize()
        )
        hmac_obj = hmac.new(derived_key, merchant_parameters.encode(), hashlib.sha256)
        return base64.urlsafe_b64encode(hmac_obj.digest()).decode()
