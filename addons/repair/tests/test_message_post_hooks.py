from odoo.tests import tagged

from odoo.addons.repair.tests.test_repair import TestRepairCommon


@tagged("mail_post")
class TestRepairMessagePostBatch(TestRepairCommon):
    def test_batch_post_notifies_a_mentioned_author(self):
        repairs = self.repair0 | self.repair1
        notified = []
        original = self.registry["repair.order"]._notify_thread

        def _notify_thread(record, message, msg_vals=False, **kwargs):
            notified.append(kwargs.get("notify_author_mention"))
            return original(record, message, msg_vals=msg_vals, **kwargs)

        self.patch(self.registry["repair.order"], "_notify_thread", _notify_thread)
        repairs._message_post_values_all(
            {
                repair.id: {"body": "Ready", "message_type": "comment"}
                for repair in repairs
            }
        )
        self.assertEqual(notified, [True, True])
