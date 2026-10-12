from hashlib import sha1
from urllib.parse import unquote_plus

from odoo import fields, models

from odoo.addons.payment_buckaroo import const


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "buckaroo_secret_key": "buckaroo_secret_key",
    }

    code = fields.Selection(
        selection_add=[("buckaroo", "Buckaroo")],
        ondelete={"buckaroo": "set default"},
    )
    buckaroo_website_key = fields.Char(
        string="Website Key",
        copy=False,
        required_if_provider="buckaroo",
        help="The key solely used to identify the website with Buckaroo",
    )
    buckaroo_secret_key = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="buckaroo",
        groups="base.group_system",
    )

    def _get_supported_currencies(self):
        supported_currencies = super()._get_supported_currencies()
        if self.code == "buckaroo":
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "buckaroo":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _buckaroo_get_api_url(self) -> str:
        self.check_singleton()
        if self.state == "enabled":
            return "https://checkout.buckaroo.nl/html/"
        else:
            return "https://testcheckout.buckaroo.nl/html/"

    def _get_buckaroo_signature(self, values, incoming=True):
        if incoming:
            items = [
                (k, unquote_plus(v))
                for k, v in values.items()
                if k.lower() != "brq_signature"
            ]
        else:
            items = values.items()
        filtered_items = [
            (k, v)
            for k, v in items
            if any(
                k.lower().startswith(key_prefix)
                for key_prefix in ("add_", "brq_", "cust_")
            )
        ]
        sorted_items = sorted(filtered_items, key=lambda pair: pair[0].lower())
        sign_string = "".join(f"{k}={v or ''}" for k, v in sorted_items)
        sign_string += self.buckaroo_secret_key
        return sha1(sign_string.encode("utf-8")).hexdigest()
