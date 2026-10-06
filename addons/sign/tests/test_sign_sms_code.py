import re
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .sign_request_common import SignRequestCommon
from odoo.addons.sign.models.sign_request_item import (
    SMS_CODE_MAX_FAILURES,
    SMS_SEND_BURST,
)


@tagged("post_install", "-at_install")
class TestSignSmsCode(SignRequestCommon):
    def setUp(self):
        super().setUp()
        sign_request = self.create_sign_request_1_role_sms_auth(
            self.partner_1, self.env["res.partner"]
        )
        self.item = sign_request.request_item_ids.sudo()
        self.item.sms_number = "+32499000001"
        patcher = patch.object(type(self.env["sms.sms"]), "send", lambda self: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _send(self):
        self.assertTrue(self.item._send_sms_code())
        sms = self.env["sms.sms"].search(
            [("number", "=", "+32499000001")], order="id desc", limit=1
        )
        return re.search(r"\d{6}", sms.body).group()

    def test_the_right_code_verifies_once(self):
        code = self._send()
        self.assertTrue(self.item._verify_sms_code(code))
        self.assertTrue(self.item.sms_verified_date)
        self.assertFalse(self.item._verify_sms_code(code))

    def test_a_new_code_voids_the_previous_one(self):
        with patch.object(
            type(self.env["sign.request.item"]),
            "_generate_sms_code",
            side_effect=["111111", "222222"],
        ):
            first = self._send()
            second = self._send()
        self.assertEqual((first, second), ("111111", "222222"))
        self.assertFalse(self.item._verify_sms_code(first))
        self.assertTrue(self.item._verify_sms_code(second))

    def test_a_code_verifies_only_for_the_number_it_was_sent_to(self):
        code = self._send()
        self.item.sms_number = "+32499000999"
        self.assertFalse(self.item._verify_sms_code(code))
        self.item.sms_number = "+32499000001"
        self.assertTrue(self.item._verify_sms_code(code))
        self.assertEqual(self.item.sms_verified_number, "+32499000001")

    def test_credits_matter_only_when_iap_sends(self):
        Item = self.env["sign.request.item"]
        credits = "odoo.addons.iap.models.iap_account.IapAccount.get_credits"
        with patch(credits, lambda self, service: 0):
            self.assertFalse(Item._has_sms_credits())
            with patch.object(
                type(self.env.company),
                "_get_sms_api_class",
                lambda company: type("OtherProvider", (), {}),
            ):
                self.assertTrue(Item._has_sms_credits())
        with patch(credits, lambda self, service: -1):
            self.assertTrue(
                Item._has_sms_credits(), "an unknown balance does not block"
            )

    def test_the_owner_is_told_once_per_request(self):
        sign_request = self.create_sign_request_2_roles(
            self.partner_1, self.partner_2, self.env["res.partner"]
        )
        for item in sign_request.request_item_ids.sudo():
            item._notify_missing_sms_credits()
            item._notify_missing_sms_credits()
        activity_type = self.env.ref("sign.mail_activity_data_sms_credits")
        self.assertEqual(
            len(
                sign_request.activity_ids.filtered(
                    lambda activity: activity.activity_type_id == activity_type
                )
            ),
            1,
        )

    def test_wrong_attempts_void_the_code(self):
        code = self._send()
        wrong = f"{(int(code) + 1) % 10**6:06d}"
        for _attempt in range(SMS_CODE_MAX_FAILURES):
            self.assertFalse(self.item._verify_sms_code(wrong))
        self.assertFalse(self.item._verify_sms_code(code))
        self.assertFalse(self.item.sms_verified_date)

    def test_an_expired_code_is_refused(self):
        code = self._send()
        self.item.sms_code_expires_at = fields.Datetime.now() - timedelta(seconds=1)
        self.assertFalse(self.item._verify_sms_code(code))

    def test_sending_is_throttled_per_signer(self):
        for _sent in range(SMS_SEND_BURST):
            self._send()
        self.assertFalse(self.item._send_sms_code())
