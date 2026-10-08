import os
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.iap.tools import iap_tools
from odoo.addons.mixin_encryption.models import mixin_encryption as encryption_module


@tagged("post_install", "-at_install")
class TestSmsWithoutIapAccount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["iap.account"].sudo().search([("service_name", "=", "sms")]).unlink()
        cls.partner = cls.env["res.partner"].create({"name": "Unreachable Recipient"})

    def test_an_sms_that_cannot_get_an_iap_account_ends_in_error(self):
        with (
            patch.dict(os.environ, clear=False) as env,
            patch.object(
                iap_tools,
                "iap_jsonrpc",
                side_effect=AssertionError("no account, no IAP call"),
            ),
            self.assertNoLogs(encryption_module._logger, "ERROR"),
        ):
            env.pop("ODOO_API_ENCRYPTION_KEY", None)
            message = self.partner._message_sms(
                "On our way",
                partner_ids=self.partner.ids,
                sms_pid_to_number={self.partner.id: "+32456010203"},
            )

        sms = self.env["sms.sms"].sudo().search([("mail_message_id", "=", message.id)])
        self.assertEqual(sms.state, "error")
        self.assertEqual(sms.failure_type, "sms_acc")
        notification = message.notification_ids.filtered(
            lambda notif: notif.notification_type == "sms"
        )
        self.assertEqual(notification.notification_status, "exception")
        self.assertEqual(notification.failure_type, "sms_acc")
        self.assertFalse(
            self.env["iap.account"].sudo().search([("service_name", "=", "sms")])
        )
