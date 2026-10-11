import base64
import json
import re
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urljoin

from requests import Response

from odoo import Command
from odoo.tests.common import TransactionCase

from odoo.addons.integration_twilio.tools.sms_api import SmsApiTwilio
from odoo.addons.integration_twilio.tools.twilio_signature import compute_signature
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.sms.models.sms_sms import SmsSms
from odoo.addons.sms.tests.common import SMSCase

ONE_PIXEL_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGMAAQAAAAUAAQ0KLbQAAAAASUVORK5CYII="
TWILIO_ACCOUNT_SID = "AC12345678987654321234567898765432"
TWILIO_AUTH_TOKEN = "grimgorironhide"


class MockSmsTwilioApi(SMSCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.twilio_valid_phone_number = "+12202154155"
        cls.twilio_invalid_phone_number = "+3212312312"

        cls.mock_error_type = False
        cls.mock_error_number_to_type = {}
        cls.mock_body = False
        cls.mock_company = cls.env.company
        cls.mock_number = False
        cls.mock_sms_uuid = "NA"

        cls.twilio_request_re = re.compile(
            r"https://api.twilio.com/2010-04-01/Accounts(?:/(AC[\d]{32}))?(?:/|\.json)?(.*)"
        )
        cls.account_json = {
            "sid": TWILIO_ACCOUNT_SID,
            "status": "active",
            "type": "Full",
        }
        cls.calls_json = {"calls": [], "next_page_uri": None}
        cls.tokens_json = {
            "ice_servers": [
                {
                    "urls": "turn:global.turn.twilio.com:3478?transport=udp",
                    "username": "u",
                    "credential": "c",
                }
            ]
        }
        cls.balance_json = {
            "account_sid": TWILIO_ACCOUNT_SID,
            "balance": "12.50",
            "currency": "USD",
        }

        cls.webhook_ok_response = {
            "AccountSid": "ACfake",
            "ApiVersion": "2010-04-01",
            "From": "+12212341234",
            "MessageSid": "SMfake",
            "MessageStatus": "delivered",
            "RawDlrDoneDate": "2504241615",
            "SmsSid": "SMfake",
            "SmsStatus": "delivered",
            "To": "+32486321321",
        }
        cls.request_send_ok_json = {
            "account_sid": "AC12345678987654321234567898765432",
            "api_version": "2010-04-01",
            "date_created": "Mon, 14 Apr 2025 09:27:41 +0000",
            "date_sent": None,
            "date_updated": "Mon, 14 Apr 2025 09:27:41 +0000",
            "direction": "outbound-api",
            "error_code": None,
            "error_message": None,
            "from": "+12212341234",
            "messaging_service_sid": None,
            "num_media": "0",
            "num_segments": "1",
            "price": None,
            "price_unit": "USD",
            "sid": "SMfake",
            "status": "queued",
            "subresource_uris": {
                "media": "/2010-04-01/Accounts/ACfake/Messages/SMfake/Media.json"
            },
            "uri": "/2010-04-01/Accounts/ACfake/Messages/SMfake.json",
        }
        cls.mock_requests = []
        cls.mock_updated_numbers = []
        cls.incoming_phone_numbers_json = {
            "incoming_phone_numbers": [
                {
                    "sid": "PN11111111111111111111111111111111",
                    "phone_number": "+32455998877",
                    "capabilities": {"sms": True, "mms": False, "voice": True},
                    "sms_url": "",
                },
                {
                    "sid": "PN22222222222222222222222222222222",
                    "phone_number": "+32455665544",
                    "capabilities": {"sms": False, "mms": False, "voice": True},
                    "sms_url": "",
                },
            ],
            "next_page_uri": None,
        }
        cls.request_send_nok_json = {
            "code": 21211,
            "more_info": "https://www.twilio.com/docs/errors/21211",
            "status": 400,
        }

    @staticmethod
    def _make_twilio_response(request, payload, status_code=200):
        response = Response()
        response.status_code = status_code
        response._content = json.dumps(payload).encode()
        response.headers["Content-Type"] = "application/json"
        response.url = request.url
        response.request = request
        return response

    @classmethod
    def _request_handler(cls, session, request, **kwargs):
        matching = cls.twilio_request_re.match(request.url)
        if not matching:
            return super()._request_handler(session, request, **kwargs)
        cls.mock_requests.append(request)
        resource = matching.group(2).split("?", 1)[0]
        if not matching.group(1):
            return cls._make_twilio_response(request, {"accounts": [cls.account_json]})
        if resource in ("", ".json"):
            return cls._make_twilio_response(request, cls.account_json)
        if resource == "Calls.json":
            return cls._make_twilio_response(request, cls.calls_json)
        if resource == "Tokens.json":
            return cls._make_twilio_response(request, cls.tokens_json)
        if resource == "Balance.json":
            return cls._make_twilio_response(request, cls.balance_json)
        if resource == "IncomingPhoneNumbers.json":
            return cls._make_twilio_response(request, cls.incoming_phone_numbers_json)
        if resource.startswith("IncomingPhoneNumbers/"):
            cls.mock_updated_numbers.append(request.body)
            return cls._make_twilio_response(request, {"sid": resource})
        if "/Media/" in resource:
            response = cls._make_twilio_response(request, {})
            response._content = base64.b64decode(ONE_PIXEL_PNG)
            response.headers["Content-Type"] = "image/png"
            return response
        if resource != "Messages.json":
            return super()._request_handler(session, request, **kwargs)
        error_type = (
            cls.mock_error_number_to_type.get(cls.mock_number) or cls.mock_error_type
        )
        if not error_type and not cls.mock_number:
            error_type = "sms_number_missing"
        error_codes = {
            "wrong_number_format": 21211,
            "sms_number_missing": 21604,
            "twilio_acc_unverified": 21608,
            "twilio_callback": 21609,
            "twilio_opted_out": 21610,
            "rate_limited": 20429,
            "unknown": 1,
            "other": 1,
        }
        if not error_type:
            payload = {
                **cls.request_send_ok_json,
                "body": cls.mock_body or "body",
                "sid": f"twilio_{cls.mock_company.name}_{cls.mock_sms_uuid}"
                if cls.mock_sms_uuid
                else "SMFake",
                "to_number": cls.mock_number or "to_number",
            }
            return cls._make_twilio_response(request, payload)
        if error_type not in error_codes:
            raise ValueError("Unsupported error code")
        payload = {
            **cls.request_send_nok_json,
            "body": cls.mock_body or "body",
            "code": error_codes[error_type],
            "to_number": cls.mock_number or "to_number",
        }
        status_code = 429 if error_type == "rate_limited" else 400
        return cls._make_twilio_response(request, payload, status_code=status_code)

    @classmethod
    def _setup_sms_twilio(cls, company):
        company.sudo().write(
            {
                "sms_provider": "twilio",
                "twilio_account_sid": TWILIO_ACCOUNT_SID,
                "twilio_auth_token": TWILIO_AUTH_TOKEN,
                "twilio_number_ids": [
                    (5, 0),
                    (
                        0,
                        0,
                        {
                            "country_id": cls.env.ref("base.be").id,
                            "number": "+32455998877",
                            "sequence": 0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "country_id": cls.env.ref("base.us").id,
                            "number": "+15056998877",
                            "sequence": 1,
                        },
                    ),
                ],
            }
        )

    @classmethod
    def _update_mock(
        cls,
        error_type=None,
        error_number_to_type=None,
        body=None,
        number=False,
        sms_uuid=False,
        company=False,
    ):
        if error_type is not None:
            cls.mock_error_type = error_type
        if error_number_to_type is not None:
            cls.mock_error_number_to_type = error_number_to_type
        if body is not None:
            cls.mock_body = body
        if company is not False:
            cls.mock_company = company
        if number is not False:
            cls.mock_number = number
        if sms_uuid is not False:
            cls.mock_sms_uuid = sms_uuid

    @contextmanager
    def mock_sms_twilio_send(self, error_type=False, error_number_to_type=None):
        self._clear_sms_sent()
        self._update_mock(
            error_type=error_type,
            error_number_to_type=error_number_to_type,
            company=self.env.company,
        )
        post_twilio_message_origin = SmsApiTwilio._post_twilio_message

        def _post_twilio_message(model, *args, **kwargs):
            (_client, to_number, body, uuid) = args
            self._update_mock(
                error_type=self.mock_error_type,
                error_number_to_type=self.mock_error_number_to_type,
                body=body,
                number=to_number,
                sms_uuid=uuid,
                company=model.company,
            )
            res = post_twilio_message_origin(model, *args, **kwargs)
            self._sms += [
                {
                    "body": body,
                    "number": to_number,
                    "uuid": uuid,
                }
            ]
            return res

        with patch.object(
            SmsApiTwilio,
            "_post_twilio_message",
            autospec=True,
            side_effect=_post_twilio_message,
        ) as _sms_twilio_send_mock:
            self._sms_twilio_send_mock = _sms_twilio_send_mock
            yield

    @contextmanager
    def mock_sms_twilio_gateway(self, error_type=False, error_number_to_type=None):
        self._clear_sms_sent()
        sms_create_origin = SmsSms.create

        def _sms_sms_create(model, *args, **kwargs):
            res = sms_create_origin(model, *args, **kwargs)
            self._new_sms += res.sudo()
            return res

        with (
            patch.object(
                SmsSms,
                "create",
                autospec=True,
                wraps=SmsSms,
                side_effect=_sms_sms_create,
            ),
            self.mock_sms_twilio_send(
                error_type=error_type, error_number_to_type=error_number_to_type
            ),
        ):
            yield

    def post_signed_twilio_callback(
        self, path, params, company=None, auth_token=None, idempotency_token=None
    ):
        company = company or self.user_admin.company_id
        signature = compute_signature(
            auth_token or TWILIO_AUTH_TOKEN,
            urljoin(company.get_base_url(), path),
            params.items(),
        )
        headers = {"X-Twilio-Signature": signature}
        if idempotency_token:
            headers["I-Twilio-Idempotency-Token"] = idempotency_token
        return self.url_open(path, params, headers=headers)

    def simulate_sms_twilio_status(self, sms_batch, company):
        for sms in sms_batch:
            message_sid = f"SM{sms.uuid}"
            self.post_signed_twilio_callback(
                f"/integration_twilio/sms/status/{sms.uuid}",
                {
                    **self.webhook_ok_response,
                    "MessageSid": message_sid,
                    "SmsSid": message_sid,
                },
            )


class MockSmsTwilio(MockSmsTwilioApi, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_admin = cls.env.ref("base.user_admin")
        cls.company_admin = cls.user_admin.company_id
        cls.basic_user = mail_new_test_user(
            cls.env,
            company_id=cls.company_admin.id,
            country_id=cls.env.ref("base.be").id,
            groups="base.group_user,base.group_partner_manager",
            login="employee",
        )

        cls.valid_partner = cls.env["res.partner"].create(
            {
                "name": "ValidPartner",
                "phone_ids": [
                    Command.create(
                        {"number": cls.twilio_valid_phone_number, "type": "landline"}
                    )
                ],
            }
        )
        cls.invalid_partner = cls.env["res.partner"].create(
            {
                "name": "InvalidPartner",
                "phone_ids": [
                    Command.create(
                        {"number": cls.twilio_invalid_phone_number, "type": "landline"}
                    )
                ],
            }
        )
