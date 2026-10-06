from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNotificationGarbageCollection(TransactionCase):
    def _old_read_notifications(self, count):
        partners = self.env["res.partner"].create(
            [{"name": f"GC reader {index}"} for index in range(count)]
        )
        message = self.env["mail.message"].create(
            {"body": "<p>old</p>", "message_type": "comment"}
        )
        notifications = self.env["mail.notification"].create(
            [
                {
                    "mail_message_id": message.id,
                    "res_partner_id": partner.id,
                    "notification_type": "inbox",
                    "notification_status": "sent",
                    "is_read": True,
                }
                for partner in partners
            ]
        )
        notifications.read_date = fields.Datetime.now() - timedelta(days=400)
        return notifications

    def test_a_backlog_beyond_one_batch_is_collected_and_resumed(self):
        notifications = self._old_read_notifications(5)
        Notification = self.env["mail.notification"]
        IrCron = type(self.env["ir.cron"])
        with (
            patch("odoo.addons.mail.models.mail_notification.GC_UNLINK_LIMIT", 2),
            patch.object(IrCron, "_commit_progress", return_value=0),
        ):
            Notification._gc_notifications()
        self.assertEqual(len(notifications.exists()), 3)
        cron = self.env.ref("mail.ir_cron_delete_notification")
        self.assertTrue(self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)]))
        with (
            patch("odoo.addons.mail.models.mail_notification.GC_UNLINK_LIMIT", 2),
            patch.object(IrCron, "_commit_progress", return_value=float("inf")),
        ):
            Notification._gc_notifications()
        self.assertFalse(notifications.exists())
