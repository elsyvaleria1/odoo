from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.website_forum.tests.common import TestForumCommon


@tagged("mail_post")
class TestForumMessagePostBatch(TestForumCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.answer_2 = cls.env["forum.post"].create(
            {
                "name": "TestAnswer2",
                "content": "I am a pangolin.",
                "forum_id": cls.forum.id,
                "parent_id": cls.post.id,
            }
        )
        cls.answers = cls.answer | cls.answer_2

    def _comment_all(self, posts):
        return posts._message_post_values_all(
            {
                post.id: {
                    "body": "Comment",
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                }
                for post in posts
            }
        )

    def test_batch_comment_checks_karma(self):
        answers = self.answers.with_user(self.user_employee)
        self.assertFalse(any(answers.mapped("can_comment")))
        with self.assertRaises(AccessError):
            self._comment_all(answers)

    def test_batch_comment_reaches_question_followers(self):
        follower = self.env["res.partner"].create(
            {"name": "Question Follower", "email": "follower@example.com"}
        )
        self.post.message_subscribe(
            partner_ids=follower.ids, subtype_ids=self.env.ref("mail.mt_comment").ids
        )
        notified = []
        original = self.registry["forum.post"]._notify_thread

        def _notify_thread(record, message, msg_vals=False, **kwargs):
            notified.append(kwargs.get("force_record_name"))
            return original(record, message, msg_vals=msg_vals, **kwargs)

        self.patch(self.registry["forum.post"], "_notify_thread", _notify_thread)
        messages = self._comment_all(self.answers)
        for message in messages:
            self.assertIn(follower, message.partner_ids)
        self.assertEqual(notified, [self.post.name, self.post.name])
