from odoo.tests.common import tagged, users

from odoo.addons.knowledge.tests.common import KnowledgeArticlePermissionsCase


@tagged("knowledge_comments", "mail_post")
class TestKnowledgeThreadPostBatch(KnowledgeArticlePermissionsCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.article = cls.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.partner_employee_manager.id,
                            "permission": "write",
                        },
                    ),
                ],
                "internal_permission": "none",
                "name": "Shared With Portal",
            }
        )
        cls.article.invite_members(cls.partner_portal, "read")
        cls.threads = (
            cls.env["knowledge.article.thread"]
            .with_context(mail_create_nolog=True)
            .create([{"article_id": cls.article.id}, {"article_id": cls.article.id}])
        )

    @users("portal_test")
    def test_portal_batch_post_keeps_only_the_content(self):
        threads = self.threads.with_env(self.env)
        messages = threads._message_post_values_all(
            {
                thread.id: {
                    "body": "Hello",
                    "message_type": "notification",
                    "partner_ids": self.env.user.partner_id.ids,
                    "subject": "Injected",
                }
                for thread in threads
            }
        )
        self.assertEqual(len(messages), 2)
        for message in messages.sudo():
            self.assertEqual(message.message_type, "comment")
            self.assertEqual(message.subtype_id, self.env.ref("mail.mt_comment"))
            self.assertFalse(message.subject)
            self.assertEqual(message.partner_ids, self.env.user.partner_id)
