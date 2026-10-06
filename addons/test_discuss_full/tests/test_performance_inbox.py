from itertools import chain

from odoo.tests.common import HttpCase, tagged, warmup

from odoo.addons.mail.tests.common import MailCommon


@tagged("post_install", "-at_install", "is_query_count")
class TestNotificationTabPerformance(HttpCase, MailCommon):
    @warmup
    def test_fetch_with_rating_stats_enabled(self):
        """
        Computation of rating_stats should run a single query per model with rating_stats enabled.
        """
        # Queries (in order):
        #   - select auth_user_client (session binding, security.is_session_valid)
        #   2: SAVEPOINT / RELEASE around the fetch param (webclient _process_one_request)
        #   - fetch res_users (current user)
        #   - search mail_message (_message_fetch, the tab's domain)
        #   - search bus_bus (_bus_last_id)
        #   25 message _to_store:
        #       - fetch mail_message
        #       - search mail_message_schedule
        #       - search mail_followers (add_followers)
        #       2 thread _to_store:
        #           - fetch slide_channel
        #           - fetch product_template
        #       - search mail_message_res_partner_starred_rel (_compute_starred)
        #       - search message_attachment_rel
        #       - search mail_message_link_preview
        #       - search mail_message_res_partner_rel
        #       - search mail_message_reaction
        #       - search mail_notification
        #       2 _filtered_for_web_client:
        #           - fetch mail_notification
        #           - fetch res_partner
        #       - fetch mail_message_subtype
        #       3 _author_to_store:
        #           - fetch res_partner
        #           - search res_users
        #           - fetch res_users
        #       - fetch rating_rating (_compute_rating_id)
        #       2 _compute_message_needaction_stats: one per thread model
        #       - search mail_tracking_value
        #       - read group rating_rating (_rating_get_stats_per_record for slide.channel)
        #       - read group rating_rating (_compute_rating_stats for slide.channel)
        #       - read group rating_rating (_rating_get_stats_per_record for product.template)
        #       - read group rating_rating (_compute_rating_stats for product.template)
        # The ir.access rows the access checks read are cached, so no query.
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
        with self.assertQueryCount(31):
            self.call_jsonrpc(
                "/mail/data", {"fetch_params": [[load_more, params, "tab"]]}
            )
