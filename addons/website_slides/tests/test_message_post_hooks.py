from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from odoo.addons.website_slides.tests import common


@tagged("mail_post")
class TestSlidesMessagePostBatch(common.SlidesCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel_2 = (
            cls.env["slide.channel"]
            .with_user(cls.user_officer)
            .create(
                {
                    "name": "Second Channel",
                    "channel_type": "documentation",
                    "enroll": "public",
                    "visibility": "public",
                    "is_published": True,
                    "karma_gen_channel_rank": 10,
                }
            )
        )
        cls.channels = cls.channel | cls.channel_2

    def _comment_all(self, records, **values):
        return records._message_post_values_all(
            {
                record.id: {
                    "body": "Nice",
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                    **values,
                }
                for record in records
            }
        )

    def test_batch_comment_on_slides_checks_karma(self):
        slides = (self.slide | self.slide_2).with_user(self.user_emp)
        self.assertFalse(slides.channel_id.can_comment)
        with self.mock_mail_gateway(), self.assertRaises(AccessError):
            self._comment_all(slides)

    def test_batch_review_on_channels_checks_karma(self):
        self.channels.sudo()._action_add_members(self.user_emp.partner_id)
        self.channels.sudo().write({"karma_review": 100})
        self.user_emp.sudo().karma = 0
        channels = self.channels.with_user(self.user_emp)
        self.assertFalse(any(channels.mapped("can_review")))
        with self.mock_mail_gateway():
            channels[0].message_post(body="Note", message_type="notification")
        with self.mock_mail_gateway(), self.assertRaises(AccessError):
            self._comment_all(channels)

    def test_batch_review_rates_once_per_course_and_gains_karma(self):
        self.channels.sudo()._action_add_members(self.user_portal.partner_id)
        self.channels.sudo().write({"karma_review": 0})
        self.user_portal.sudo().karma = 50
        channels = self.channels.with_user(self.user_portal)
        with self.mock_mail_gateway():
            messages = self._comment_all(channels, rating_value=4)
        self.assertEqual(messages.mapped("rating_value"), [4, 4])
        self.assertEqual(self.user_portal.karma, 50 + 10 + 10)
        with self.mock_mail_gateway(), self.assertRaises(ValidationError):
            self._comment_all(channels, rating_value=5)

    def test_batch_reply_to_publication_is_a_note(self):
        published = self.env.ref("website_slides.mt_channel_slide_published")
        parents = {
            channel.id: channel.message_post(
                body="Published", subtype_id=published.id
            ).id
            for channel in self.channels
        }
        comment = self.env.ref("mail.mt_comment")
        with self.mock_mail_gateway():
            messages = self.channels._message_post_values_all(
                {
                    channel.id: {
                        "body": "Reply",
                        "message_type": "comment",
                        "parent_id": parents[channel.id],
                        "subtype_id": comment.id,
                    }
                    for channel in self.channels
                }
            )
        self.assertEqual(messages.subtype_id, self.env.ref("mail.mt_note"))
