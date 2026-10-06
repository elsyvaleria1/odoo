from odoo.tests import tagged, users
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from odoo.addons.integration_twilio.tests.common import MockSmsTwilio


@tagged("post_install", "-at_install", "twilio", "twilio_controller")
class TestSmsTwilioController(MockSmsTwilio, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.user_admin.company_id)

    @mute_logger("odoo.addons.integration_twilio.controllers.main")
    @users("employee")
    def test_sms_twilio_controller_status(self):
        """Test that the controller correctly processes the webhook calls we
        receive from Twilio"""
        # All good
        ok = self.webhook_ok_response.copy()
        # Handle known errors (the ones that we have already mapped)
        invalid_destination = {
            **self.webhook_ok_response,
            "MessageStatus": "undelivered",
            "SmsStatus": "undelivered",
            "ErrorCode": 30005,
            "ErrorMessage": "Unknown destination handset",
        }
        # Handle unknown errors (the ones that we not have mapped)
        unknown_error = {
            **self.webhook_ok_response,
            "MessageStatus": "failed",
            "SmsStatus": "failed",
            "ErrorCode": 12345,
            "ErrorMessage": "Unknown error",
        }
        # Unknown status -> no update
        wrong_status = {
            **self.webhook_ok_response,
            "MessageStatus": "myfakestatus",
            "SmsStatus": "myfakestatus",
            "ErrorCode": 12345,
            "ErrorMessage": "Unknown error",
        }
        with self.mock_sms_twilio_gateway():
            for call_params, expected_data in zip(
                [ok, invalid_destination, unknown_error, wrong_status],
                [
                    {
                        "failure_type": False,
                        "failure_reason": False,
                        "notification_status": "sent",
                    },
                    {
                        "failure_type": "sms_invalid_destination",
                        "failure_reason": "Unknown destination handset",
                        "notification_status": "bounce",
                    },
                    {
                        "failure_type": "unknown",
                        "failure_reason": "Unknown error",
                        "notification_status": "exception",
                    },
                    {
                        "failure_type": False,
                        "failure_reason": False,
                        "notification_status": "pending",
                    },
                ],
                strict=True,
            ):
                with self.subTest(call_params=call_params):
                    composer = (
                        self.env["wizard.sms.sms.send"]
                        .with_context(
                            active_model="res.partner",
                            active_id=self.valid_partner,
                        )
                        .create({"body": "SMS Body"})
                    )
                    composer._action_send_sms()
                    sms = self._new_sms[-1]

                    self.post_signed_twilio_callback(
                        f"/integration_twilio/sms/status/{sms.uuid}", call_params
                    )
                    self.assertRecordValues(
                        sms.sms_tracker_id.mail_notification_id,
                        [
                            {
                                "notification_status": expected_data[
                                    "notification_status"
                                ],
                                "failure_type": expected_data["failure_type"],
                                "failure_reason": expected_data["failure_reason"],
                            }
                        ],
                    )

    @mute_logger("odoo.addons.integration_twilio.controllers.main")
    @users("employee")
    def test_sms_twilio_controller_status_signature(self):
        """Check X-Twilio-Signature is effectively checked"""
        call_params = self.webhook_ok_response.copy()
        with self.mock_sms_twilio_gateway():
            composer = (
                self.env["wizard.sms.sms.send"]
                .with_context(
                    active_model="res.partner",
                    active_id=self.valid_partner,
                )
                .create({"body": "Body msg"})
            )
            composer._action_send_sms()
            sms = self._new_sms[-1]

            response = self.url_open(
                f"/integration_twilio/sms/status/{sms.uuid}",
                call_params,
                headers={
                    "X-Twilio-Signature": "WrongSignature",
                },
            )
            self.assertEqual(response.status_code, 401)
            # SMS not updated
            self.assertRecordValues(
                sms.sms_tracker_id.mail_notification_id,
                [
                    {
                        "notification_status": "pending",
                        "failure_type": False,
                        "failure_reason": False,
                    }
                ],
            )

    @users("employee")
    def test_sms_twilio_controller_refuses_a_non_ascii_signature(self):
        with self.mock_sms_twilio_gateway():
            composer = (
                self.env["wizard.sms.sms.send"]
                .with_context(active_model="res.partner", active_id=self.valid_partner)
                .create({"body": "Body msg"})
            )
            composer._action_send_sms()
            sms = self._new_sms[-1]
            with self.assertLogs(
                "odoo.addons.integration_twilio.models.integration_twilio_config",
                "WARNING",
            ):
                response = self.url_open(
                    f"/integration_twilio/sms/status/{sms.uuid}",
                    self.webhook_ok_response.copy(),
                    headers={"X-Twilio-Signature": "é" * 28},
                )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            sms.sms_tracker_id.mail_notification_id.notification_status, "pending"
        )

    def _send_one_sms(self):
        composer = (
            self.env["wizard.sms.sms.send"]
            .with_context(active_model="res.partner", active_id=self.valid_partner)
            .create({"body": "Body msg"})
        )
        composer._action_send_sms()
        return self._new_sms[-1]

    def _status_receiver(self):
        return (
            self.env["integration.receiver"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("res_model", "=", "res.company"),
                    ("res_id", "=", self.user_admin.company_id.id),
                    ("res_purpose", "=", "twilio_sms_status"),
                ]
            )
        )

    @mute_logger(
        "odoo.addons.integration_twilio.models.integration_twilio_config",
        "odoo.addons.integration.models.mixin_inbound_gate",
    )
    @users("employee")
    def test_status_signature_cannot_be_switched_off_on_the_receiver(self):
        with self.mock_sms_twilio_gateway():
            sms = self._send_one_sms()
            path = f"/integration_twilio/sms/status/{sms.uuid}"
            self.post_signed_twilio_callback(path, self.webhook_ok_response)
            receiver = self._status_receiver()
            self.assertEqual(len(receiver), 1)
            receiver.auth_type = "none"
            response = self.url_open(
                path,
                {**self.webhook_ok_response, "MessageStatus": "failed"},
                headers={"X-Twilio-Signature": "forged"},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            sms.sms_tracker_id.mail_notification_id.notification_status, "sent"
        )

    @mute_logger("odoo.addons.integration.models.mixin_inbound_gate")
    @users("employee")
    def test_archived_status_receiver_refuses(self):
        with self.mock_sms_twilio_gateway():
            sms = self._send_one_sms()
            path = f"/integration_twilio/sms/status/{sms.uuid}"
            self.post_signed_twilio_callback(
                path,
                {
                    **self.webhook_ok_response,
                    "MessageStatus": "sent",
                    "SmsStatus": "sent",
                },
            )
            self._status_receiver().active = False
            response = self.post_signed_twilio_callback(path, self.webhook_ok_response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            sms.sms_tracker_id.mail_notification_id.notification_status, "pending"
        )

    @users("employee")
    def test_redelivered_status_is_acknowledged_once(self):
        with self.mock_sms_twilio_gateway():
            sms = self._send_one_sms()
            path = f"/integration_twilio/sms/status/{sms.uuid}"
            first = self.post_signed_twilio_callback(
                path, self.webhook_ok_response, idempotency_token="retry-1"
            )
            notification = sms.sms_tracker_id.mail_notification_id
            notification.notification_status = "pending"
            again = self.post_signed_twilio_callback(
                path, self.webhook_ok_response, idempotency_token="retry-1"
            )
        self.assertEqual((first.status_code, again.status_code), (200, 200))
        self.assertIn("<Response/>", again.text)
        self.assertEqual(notification.notification_status, "pending")

    @users("employee")
    def test_status_on_the_former_route(self):
        with self.mock_sms_twilio_gateway():
            sms = self._send_one_sms()
            response = self.post_signed_twilio_callback(
                f"/sms_twilio/status/{sms.uuid}", self.webhook_ok_response
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sms.sms_tracker_id.mail_notification_id.notification_status, "sent"
        )
