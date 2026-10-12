import pprint

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.libs.json import dumps as json_dumps

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_authorize import const
from odoo.addons.payment_authorize.models.authorize_request import AuthorizeAPI

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "authorize_transaction_key": "authorize_transaction_key",
        "authorize_signature_key": "authorize_signature_key",
    }

    code = fields.Selection(
        selection_add=[("authorize", "Authorize.Net")],
        ondelete={"authorize": "set default"},
    )
    authorize_login = fields.Char(
        string="API Login ID",
        copy=False,
        required_if_provider="authorize",
        help="The ID solely used to identify the account with Authorize.Net",
    )
    authorize_transaction_key = fields.Char(
        string="API Transaction Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="authorize",
        groups="base.group_system",
    )
    authorize_signature_key = fields.Char(
        string="API Signature Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="authorize",
        groups="base.group_system",
    )
    authorize_client_key = fields.Char(
        string="API Client Key",
        copy=False,
        help="The public client key. To generate directly from Odoo or from Authorize.Net backend.",
    )

    @api.constrains("available_currency_ids", "state")
    def _check_available_currency_ids(self) -> None:
        super()._check_available_currency_ids()
        self.filtered(lambda p: p.code == "authorize")._check_single_available_currency(
            self.env._("Only one currency can be selected by Authorize.Net account.")
        )

    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "authorize").update(
            {
                "support_manual_capture": "full_only",
                "support_refund": "full_only",
                "support_tokenization": True,
            }
        )

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "authorize":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def action_update_merchant_details(self) -> None:
        self.check_singleton()

        if self.state == "disabled":
            raise UserError(
                self.env._(
                    "This action cannot be performed while the provider is disabled."
                )
            )

        authorize_API = AuthorizeAPI(self)

        res_content = authorize_API.test_authenticate()
        _logger.info(
            "test_authenticate request response:\n%s", pprint.pformat(res_content)
        )
        if res_content.get("err_msg"):
            raise UserError(
                self.env._("Failed to authenticate.\n%s", res_content["err_msg"])
            )

        res_content = authorize_API.merchant_details()
        _logger.info(
            "merchant_details request response:\n%s", pprint.pformat(res_content)
        )
        if res_content.get("err_msg"):
            raise UserError(
                self.env._(
                    "Could not fetch merchant details:\n%s", res_content["err_msg"]
                )
            )

        currency = self.env["res.currency"].search(
            [("name", "in", res_content.get("currencies"))]
        )
        self.available_currency_ids = [Command.set(currency.ids)]
        self.authorize_client_key = res_content.get("publicClientKey")

    def _get_validation_amount(self):
        res = super()._get_validation_amount()
        if self.code != "authorize":
            return res

        return 0.01

    def _authorize_get_inline_form_values(self):
        self.check_singleton()

        inline_form_values = {
            "state": self.state,
            "login_id": self.authorize_login,
            "client_key": self.authorize_client_key,
        }
        return json_dumps(inline_form_values)
