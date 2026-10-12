from odoo import exceptions
from odoo.tests.common import tagged, users
from odoo.tools import mute_logger

from odoo.addons.knowledge.tests.common import KnowledgeCommonWData


@tagged("knowledge_acl")
class TestWKnowledgeSecurity(KnowledgeCommonWData):
    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    @users("user_public")
    def test_models_as_public(self):
        article_shared = self.article_shared.with_env(self.env)
        with self.assertRaises(
            exceptions.AccessError,
            msg="ACLs: Internal permission 'none', not for public",
        ):
            article_shared.body

        article_shared.sudo().website_published = True
        article_shared.body
        self.assertFalse(article_shared.is_user_favorite)

        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: No favorite access to public"
        ):
            self.env["knowledge.article.favorite"].search([])

        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: No stage access to public"
        ):
            self.env["knowledge.article.stage"].search([])

    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    @users("portal_test")
    def test_models_as_portal(self):
        article_shared = self.article_shared.with_env(self.env)
        with self.assertRaises(
            exceptions.AccessError,
            msg="ACLs: Internal permission 'none', not for portal",
        ):
            article_shared.body

        self.assertEqual(self.env["knowledge.article.stage"].search_count([]), 0)
        article_shared.sudo().website_published = True
        self.assertEqual(self.env["knowledge.article.stage"].search_count([]), 2)
        article_shared.body
        self.assertFalse(article_shared.is_user_favorite)

        article_shared.action_toggle_user_favorite()
        article_shared.invalidate_model(["is_user_favorite"])
        self.assertTrue(article_shared.is_user_favorite)

    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    @users("employee")
    def test_models_as_user(self):
        article_hidden = self.private_children[0].with_env(self.env)
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: 'none' internal permission"
        ):
            article_hidden.body

        self.assertEqual(self.env["knowledge.article.stage"].search_count([]), 2)
        article_hidden.sudo().website_published = True
        self.assertEqual(self.env["knowledge.article.stage"].search_count([]), 4)
        article_hidden.body
        self.assertFalse(article_hidden.is_user_favorite)

        article_hidden.action_toggle_user_favorite()
        article_hidden.invalidate_model(["is_user_favorite"])
        self.assertTrue(article_hidden.is_user_favorite)
