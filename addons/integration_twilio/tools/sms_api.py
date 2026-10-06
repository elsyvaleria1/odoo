import logging
from urllib.parse import urljoin

from odoo.addons.integration.tools import CommError
from odoo.addons.sms.tools.sms_api import SmsApiBase

_logger = logging.getLogger(__name__)

STATUS_ROUTE = "/integration_twilio/sms/status/"

# https://www.twilio.com/docs/api/errors/<code>
TWILIO_CODE_TO_PROVIDER_STATE = {
    20003: "twilio_authentication",
    21211: "wrong_number_format",
    21265: "wrong_number_format",
    21266: "twilio_from_to",
    21603: "twilio_from_missing",
    21604: "sms_number_missing",
    21606: "twilio_from_missing",
    21608: "twilio_acc_unverified",
    21609: "twilio_callback",
    21408: "country_not_supported",
    21610: "twilio_opted_out",
    21614: "wrong_number_format",
    21660: "twilio_from_missing",
}


def get_status_callback_url(company, uuid) -> str:
    # Twilio cannot reach localhost: a local test needs a public base URL
    return urljoin(company.get_base_url(), f"{STATUS_ROUTE}{uuid}")


class SmsApiTwilio(SmsApiBase):
    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
        "twilio_acc_unverified": "sms_acc",
        "twilio_authentication": "twilio_authentication",
        "twilio_callback": "twilio_callback",
        "twilio_from_missing": "twilio_from_missing",
        "twilio_from_to": "twilio_from_to",
        "twilio_opted_out": "sms_optout",
        "country_not_supported": "sms_country_not_supported",
    }

    def __init__(self, env, account=None) -> None:
        super().__init__(env, account=account)
        self.sender = None

    def _set_sender(self, number) -> None:
        self.sender = number

    def _post_twilio_message(self, client, to_number, body, uuid) -> dict | None:
        company = client.company
        sender = self.sender or company._get_twilio_sender(to_number)
        data = {
            # an empty From, not 'False', so Twilio names the missing sender
            "From": sender.number or "",
            "To": to_number,
            "Body": body,
            "StatusCallback": get_status_callback_url(company, uuid),
        }
        try:
            return client.request("POST", client.account_url("Messages"), data=data)
        except CommError as error:
            _logger.warning("Twilio SMS API error: %s", error)
        return None

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        # besides each SMS's uuid and state, a sent one carries Twilio's sid
        company = self.company or self.env.company
        client = company.integration_twilio_config_id._get_twilio_client()
        error_messages = self._get_sms_api_error_messages()
        results = []
        for message in messages:
            body = message.get("content") or ""
            for number_info in message.get("numbers") or []:
                uuid = number_info["uuid"]
                response = self._post_twilio_message(
                    client, number_info["number"], body, uuid
                )
                result = {
                    "failure_reason": self.env._(
                        "Twilio could not be reached; resend the SMS later"
                    ),
                    "state": "server_error",
                    "uuid": uuid,
                }
                # a 429 or a 5xx is Twilio refusing for now, not this message:
                # it stays a server error the user can resend
                if response is not None and (
                    response["status_code"] == 429 or response["status_code"] >= 500
                ):
                    result["failure_reason"] = self.env._(
                        "Twilio is busy or unavailable; resend the SMS later"
                    )
                elif response is not None:
                    answer = (
                        response["body"] if isinstance(response["body"], dict) else {}
                    )
                    if response["status_code"] >= 400 or answer.get("error_code"):
                        provider_state = self._get_provider_state(answer)
                        result |= {
                            "failure_reason": answer.get("message")
                            or answer.get("error_message")
                            or error_messages.get(provider_state),
                            "failure_type": provider_state,
                            "state": provider_state,
                        }
                    else:
                        result |= {
                            "failure_reason": False,
                            "failure_type": False,
                            "twilio_message_sid": answer.get("sid"),
                            "state": "sent",
                        }
                results.append(result)
        return results

    def _get_provider_state(self, answer) -> str:
        error_code = answer.get("code") or answer.get("error_code")
        state = TWILIO_CODE_TO_PROVIDER_STATE.get(error_code)
        if state is None:
            _logger.warning(
                'Twilio SMS: unknown error "%s" (code: %s)',
                answer.get("message"),
                error_code,
            )
            return "unknown"
        return state

    def _get_sms_api_error_messages(self):
        return super()._get_sms_api_error_messages() | {
            "sms_acc": self.env._("Trial Account Limitation"),
            "sms_number_missing": self.env._("A 'To' phone number is required"),
            "twilio_acc_unverified": self.env._(
                "The Twilio account may not send to this recipient yet: a trial "
                "account, or one without an approved compliance profile"
            ),
            "twilio_opted_out": self.env._(
                "The recipient replied STOP to this number; Twilio refuses to "
                "send until they reply START"
            ),
            "twilio_authentication": self.env._("Twilio Authentication Error"),
            "twilio_callback": self.env._("Twilio StatusCallback URL is incorrect"),
            "twilio_from_missing": self.env._(
                "A 'From' number is required to send a message"
            ),
            "twilio_from_to": self.env._("'To' and 'From' numbers cannot be the same"),
            "wrong_number_format": self.env._(
                "The number you're trying to reach is not correctly formatted"
            ),
            "unknown": self.env._("Unknown error, please contact Odoo support"),
        }
