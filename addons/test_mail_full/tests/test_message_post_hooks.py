from datetime import datetime

from markupsafe import Markup

from odoo.tests import tagged, users
from odoo.tools import plaintext2html

from odoo.addons.test_mail_full.tests.test_rating import TestRatingCommon


@tagged("mail_post", "post_install", "-at_install")
class TestMessagePostHooksBatch(TestRatingCommon):
    def _trace_notify(self, model):
        calls = []
        original = self.registry[model]._notify_thread

        def _notify_thread(record, message, msg_vals=False, **kwargs):
            calls.append((record.id, kwargs))
            return original(record, message, msg_vals=msg_vals, **kwargs)

        self.patch(self.registry[model], "_notify_thread", _notify_thread)
        return calls

    @users("employee")
    def test_rating_value_creates_one_rating_per_record_in_a_batch(self):
        records = self.env["mail.test.rating"].create(
            [{"name": "Rated 1"}, {"name": "Rated 2"}]
        )
        with self.mock_mail_gateway():
            messages = records._message_post_values_all(
                {
                    record.id: {
                        "body": Markup("<p>Great</p>"),
                        "message_type": "comment",
                        "rating_value": 4,
                        "subtype_xmlid": "mail.mt_comment",
                    }
                    for record in records
                }
            )
        self.assertEqual(len(messages), 2)
        for record, message in zip(records, messages, strict=True):
            rating = record.rating_ids
            self.assertEqual(len(rating), 1)
            self.assertEqual(rating.rating, 4)
            self.assertEqual(rating.feedback, "Great")
            self.assertEqual(rating.message_id, message)
            self.assertEqual(message.rating_value, 4)

    @users("employee")
    def test_sms_body_is_rendered_and_kept_as_content_in_a_batch(self):
        single, *records = self.env["mail.test.rating"].create(
            [{"name": "Sms 0"}, {"name": "Sms 1"}, {"name": "Sms 2"}]
        )
        records = single.browse([record.id for record in records])
        body = "Hello https://www.example.com/page"
        notified = self._trace_notify("mail.test.rating")
        with self.mock_mail_gateway():
            expected = single.message_post(body=body, message_type="sms").body
            messages = records._message_post_values_all(
                {record.id: {"body": body, "message_type": "sms"} for record in records}
            )
        self.assertIn(plaintext2html(body, with_paragraph=False), expected)
        self.assertEqual(messages.mapped("body"), [expected] * 2)
        self.assertEqual(
            [(res_id, kwargs.get("sms_content")) for res_id, kwargs in notified],
            [(record.id, body) for record in single | records],
        )


@tagged("mail_post", "discuss", "post_install", "-at_install")
class TestDiscussChannelPostHooksBatch(TestRatingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Channel = cls.env["discuss.channel"].with_user(cls.user_employee)
        cls.channels = Channel._create_group(
            partners_to=cls.partner_admin.ids, name="G1"
        ) | Channel._create_group(partners_to=cls.partner_admin.ids, name="G2")
        cls.channels.sudo().last_interest_dt = datetime(2020, 1, 1)

    @users("employee")
    def test_batch_comment_filters_recipients_and_never_subscribes(self):
        channels = self.channels.with_env(self.env)
        with self.mock_mail_gateway():
            messages = channels._message_post_values_all(
                {
                    channel.id: {
                        "body": "hello",
                        "message_type": "comment",
                        "partner_ids": [self.partner_1.id, self.partner_admin.id],
                        "subtype_xmlid": "mail.mt_comment",
                    }
                    for channel in channels
                }
            )
        self.assertEqual(len(messages), 2)
        for message in messages:
            self.assertEqual(
                message.partner_ids,
                self.partner_admin,
                "a partner outside the channel is dropped, not refused",
            )
        self.assertFalse(channels.sudo().message_follower_ids)
        for channel in channels.sudo():
            self.assertGreater(channel.last_interest_dt, datetime(2020, 1, 1))

    @users("employee")
    def test_batch_mention_everyone_notifies_every_member(self):
        channels = self.channels.with_env(self.env)
        with self.mock_mail_gateway():
            messages = channels._message_post_values_all(
                {
                    channel.id: {
                        "body": "@everyone",
                        "message_type": "comment",
                        "special_mentions": ["everyone"],
                        "subtype_xmlid": "mail.mt_comment",
                    }
                    for channel in channels
                }
            )
        for channel, message in zip(channels, messages, strict=True):
            self.assertEqual(
                message.partner_ids, channel.sudo().channel_member_ids.partner_id
            )
