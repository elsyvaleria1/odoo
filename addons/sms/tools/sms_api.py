from odoo import exceptions
from odoo.libs.debug_log import DebugLog
from odoo.tools.translate import LazyTranslate

from odoo.addons.iap.tools import iap_tools

_lt = LazyTranslate(__name__)
_debug = DebugLog(__name__)

ERROR_MESSAGES = {
    "format_error": _lt(
        "Your sender name must be between 3 and 11 characters long and only contain alphanumeric characters."
    ),
    "unregistered_account": _lt("Your sms account has not been activated yet."),
    "existing_sender": _lt(
        "This account already has an existing sender name and it cannot be changed."
    ),
    "invalid_phone_number": _lt(
        "Invalid phone number. Please make sure to follow the international format, i.e. a plus sign (+), then country code, city code, and local phone number. For example: +1 555-555-555"
    ),
    "verification_sms_delivery": _lt(
        "We were not able to reach you via your phone number. "
        "If you have requested multiple codes recently, please retry later."
    ),
    "closed_feature": _lt(
        "The SMS Service is currently unavailable for new users and new accounts registrations are suspended."
    ),
    "banned_account": _lt(
        "This phone number/account has been banned from our service."
    ),
    "invalid_code": _lt("The verification code is incorrect."),
    "no_sms_account": _lt("We were not able to find your account in our database."),
    "too_many_attempts": _lt("You tried too many times. Please retry later."),
    "unknown_error": _lt(
        "An unknown error occurred. Please contact Odoo support if this error persists."
    ),
}


class SmsApiBase:
    PROVIDER_TO_SMS_FAILURE_TYPE = {
        "server_error": "sms_server",
        "sms_number_missing": "sms_number_missing",
        "wrong_number_format": "sms_number_format",
    }

    def __init__(self, env, account=None) -> None:
        self.env = env
        self.company = env.company

    def _get_sms_api_error_messages(self):
        return {}

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        raise NotImplementedError

    def _set_company(self, company) -> None:
        self.company = company


class SmsApi(
    SmsApiBase
):
    DEFAULT_ENDPOINT = "https://sms.api.odoo.com"
    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
        "country_not_supported": "sms_country_not_supported",
        "insufficient_credit": "sms_credit",
        "unregistered": "sms_acc",
    }

    def __init__(self, env, account=None) -> None:
        super().__init__(env, account=account)
        self._account = account

    @property
    def account(self):
        return self._acquire_account()

    def _acquire_account(self):
        if not self._account:
            self._account = self.env["iap.account"].acquire_account("sms")
        return self._account

    def _contact_iap(self, local_endpoint, params, timeout=15):
        if (
            not self.env.registry.ready
        ):
            raise exceptions.AccessError("Unavailable during module installation.")  # noqa: E8505 -- a guard against reaching IAP during module installation

        params["account_token"] = self.account.sudo().account_token
        params["dbuuid"] = self.env.registry.settings.get(
            self.env, "database.uuid", False
        )
        endpoint = self.env.registry.settings.get(
            self.env, "sms.endpoint", self.DEFAULT_ENDPOINT
        )
        return iap_tools.iap_jsonrpc(
            endpoint + local_endpoint, params=params, timeout=timeout, env=self.env
        )

    def _send_sms_batch(
        self, messages, delivery_reports_url=False
    ):
        try:
            self._acquire_account()
        except exceptions.UserError as error:
            _debug.logic(
                "send_refused",
                reason="no_iap_account",
                company=self.env.company.id,
                count=sum(len(message["numbers"]) for message in messages),
            )
            return [
                {
                    "uuid": number["uuid"],
                    "state": "unregistered",
                    "failure_reason": str(error),
                }
                for message in messages
                for number in message["numbers"]
            ]
        return self._contact_iap(
            "/api/sms/3/send",
            {
                "messages": messages,
                "webhook_url": delivery_reports_url,
                "dbuuid": self.env.registry.settings.get(
                    self.env, "database.uuid", False
                ),
            },
        )

    def _get_sms_api_error_messages(self):
        buy_credits_url = (
            self.env["iap.account"].sudo().get_credits_url(service_name="sms")
        )
        buy_credits = '<a href="{}" target="_blank">{}</a>'.format(
            buy_credits_url, self.env._("Buy credits.")
        )

        error_dict = super()._get_sms_api_error_messages()
        error_dict.update(
            {
                "unregistered": self.env._("You don't have an eligible IAP account."),
                "insufficient_credit": " ".join(
                    [
                        self.env._(
                            "You don't have enough credits on your IAP account."
                        ),
                        buy_credits,
                    ]
                ),
                "wrong_number_format": self.env._(
                    "The number you're trying to reach is not correctly formatted."
                ),
                "duplicate_message": self.env._(
                    "This SMS has been removed as the number was already used."
                ),
                "country_not_supported": self.env._(
                    "The destination country is not supported."
                ),
                "incompatible_content": self.env._(
                    "The content of the message violates rules applied by our providers."
                ),
            }
        )
        return error_dict

    def _send_verification_sms(self, phone_number):
        return self._contact_iap(
            "/api/sms/1/account/create",
            {
                "phone_number": phone_number,
            },
        )

    def _confirm_account(self, verification_code):
        return self._contact_iap(
            "/api/sms/2/account/verify",
            {
                "code": verification_code,
            },
        )

    def _set_sender_name(self, sender_name):
        return self._contact_iap(
            "/api/sms/1/account/update_sender",
            {
                "sender_name": sender_name,
            },
        )
