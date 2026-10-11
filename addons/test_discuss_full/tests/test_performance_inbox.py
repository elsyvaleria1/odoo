from itertools import chain

from odoo.tests.common import HttpCase, tagged, warmup

from odoo.addons.mail.tests.common import MailCommon


@tagged("post_install", "-at_install", "is_query_count")
class TestNotificationTabPerformance(HttpCase, MailCommon):
    @warmup
    def test_fetch_with_rating_stats_enabled(self):
        first_model_records = self.env["product.template"].create(
            [{"name": "Product A1"}, {"name": "Product A2"}]
        )
        second_model_records = self.env["slide.channel"].create(
            [{"name": "Course B1"}, {"name": "Course B2"}]
        )
        for record in chain(first_model_records, second_model_records):
            record.message_post(
                body=f"<p>Test message for {record.name}</p>",
                message_type="comment",
                partner_ids=[self.user_employee.partner_id.id],
                rating_value="4",
            )
        self.authenticate(self.user_employee.login, self.user_employee.password)
        load_more = "/mail/messaging_menu/mail.message/load_more"
        params = {
            "tab_id": "notification",
            "filter_ids": ["notification_unread"],
            "limit": 30,
        }
        with self.assertQueryCount(35):
            self.call_jsonrpc(
                "/mail/data", {"fetch_params": [[load_more, params, "tab"]]}
            )
