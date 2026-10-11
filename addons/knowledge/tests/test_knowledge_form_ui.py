import base64
import io
import os
import re
from datetime import timedelta
from unittest import skipIf

from markupsafe import Markup
from PIL import Image

from odoo import fields
from odoo.tests.common import tagged, users

from odoo.addons.base.tests.common import HttpCaseWithUserDemo
from odoo.addons.mail.tests.common import MailCase


class TestKnowledgeUICommon(HttpCaseWithUserDemo, MailCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["knowledge.article"].with_context(active_test=False).search([]).unlink()

        cls.user_portal = cls._create_portal_user()

        cls.env.ref("base.user_admin").write({"email": "test.admin@test.example.com"})


@tagged("post_install", "-at_install", "knowledge", "knowledge_tour")
class TestKnowledgeUI(TestKnowledgeUICommon):
    def test_knowledge_history(self):
        self.start_tour("/odoo?debug=1", "knowledge_history_tour", login="demo")

    def test_knowledge_load_template(self):
        category = self.env["knowledge.article.template.category"].create(
            {"name": "Personal"}
        )
        template = self.env["knowledge.article"].create(
            {
                "icon": "📚",
                "article_properties_definition": [
                    {
                        "name": "28db68689e91de10",
                        "type": "char",
                        "string": "My Text Field",
                        "default": "",
                    }
                ],
                "is_template": True,
                "template_name": "My Template",
                "template_category_id": category.id,
                "template_body": Markup(
                    "<p>Lorem ipsum dolor sit amet, consectetur adipisicing elit.</p>"
                ),
            }
        )

        self.start_tour("/odoo", "knowledge_load_template", login="admin")
        article = self.env["knowledge.article"].search(
            [("origin_template_id", "=", template.id)]
        )
        self.assertEqual(len(article), 1)

        body = re.sub(r'\s*data-last-history-steps="[^"]*"', "", article.body)
        body = re.sub(r'\s*data-oe-version="[^"]*"', "", body)

        self.assertEqual(template.template_body, body)
        self.assertEqual(template.icon, article.icon)
        self.assertEqual(
            template.article_properties_definition,
            article.article_properties_definition,
        )

    def test_knowledge_main_flow(self):

        self.patch(
            self.env.cr, "now", lambda: fields.Datetime.now() - timedelta(days=1)
        )
        article_1 = self.env["knowledge.article"].create(
            {
                "name": "Article 1",
                "active": False,
                "to_delete": True,
            }
        )
        article_1.flush_recordset()

        self.patch(self.env.cr, "now", fields.Datetime.now)
        self.env["knowledge.article"].create(
            {
                "name": "Article 2",
                "active": False,
                "to_delete": True,
            }
        )
        self.env["knowledge.article"].create(
            {
                "name": "Article 3",
                "internal_permission": "write",
                "parent_id": False,
                "is_article_visible_by_everyone": True,
            }
        )
        with self.mock_mail_gateway(), self.mock_mail_app():
            self.start_tour("/odoo", "knowledge_main_flow_tour", login="admin")

        private_article = self.env["knowledge.article"].search(
            [("name", "=", "My Private Article")]
        )
        self.assertTrue(bool(private_article))
        self.assertEqual(private_article.category, "private")
        self.assertEqual(private_article.internal_permission, "none")

        workspace_article = self.env["knowledge.article"].search(
            [("name", "=", "My Workspace Article")]
        )
        self.assertTrue(bool(workspace_article))
        self.assertEqual(workspace_article.category, "workspace")
        self.assertEqual(workspace_article.internal_permission, "write")

        children_workspace_articles = workspace_article.child_ids.sorted("sequence")
        self.assertEqual(len(children_workspace_articles), 2)

        child_article_1 = children_workspace_articles.filtered(
            lambda article: article.name == "Child Article 1"
        )
        child_article_2 = children_workspace_articles.filtered(
            lambda article: article.name == "Child Article 2"
        )

        self.assertEqual(children_workspace_articles[0], child_article_2)
        self.assertEqual(children_workspace_articles[1], child_article_1)

        invited_member = workspace_article.article_member_ids.filtered(
            lambda member: member.partner_id != workspace_article.create_uid.partner_id
        )
        self.assertEqual(len(invited_member), 1)
        invited_partner = invited_member.partner_id
        self.assertEqual(len(invited_partner), 1)
        self.assertEqual(invited_partner.name, "micheline@knowledge.com")
        self.assertEqual(invited_partner.email, "micheline@knowledge.com")
        invitation_message = self.env["mail.message"].search(
            [("partner_ids", "in", invited_partner.id)]
        )
        self.assertEqual(len(invitation_message), 1)
        self.assertIn(
            workspace_article._get_invite_url(invited_partner),
            self._new_mails.body_html,
        )

        article_favorites = self.env["knowledge.article.favorite"].search([])
        self.assertEqual(len(article_favorites), 2)
        self.assertEqual(article_favorites[0].article_id, private_article)
        self.assertEqual(article_favorites[1].article_id, workspace_article)

    def test_knowledge_main_flow_portal(self):

        self.patch(self.env.cr, "now", fields.Datetime.now)

        self.env["knowledge.article"].create(
            [
                {
                    "name": "Internal Workspace Article",
                    "internal_permission": "write",
                    "parent_id": False,
                    "is_article_visible_by_everyone": True,
                },
                {
                    "name": "Workspace Article",
                    "body": "<p>Content of Workspace Article</p>",
                    "internal_permission": "write",
                    "parent_id": False,
                    "is_article_visible_by_everyone": True,
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.user_portal.partner_id.id,
                                "permission": "write",
                            },
                        )
                    ],
                },
            ]
        )

        self.start_tour(
            "/knowledge/home", "knowledge_main_flow_tour_portal", login="portal_test"
        )

        private_article = self.env["knowledge.article"].search(
            [("name", "=", "My Private Article")]
        )
        self.assertTrue(bool(private_article))
        self.assertEqual(private_article.category, "private")
        self.assertEqual(private_article.internal_permission, "none")

        workspace_article = self.env["knowledge.article"].search(
            [("name", "=", "Workspace Article")]
        )
        self.assertIn(
            "Edited Content of Workspace Article",
            workspace_article.body,
            "Portal should have been able to modify the article content as he as direct access",
        )

        children_workspace_articles = workspace_article.child_ids.sorted("sequence")
        self.assertEqual(
            len(children_workspace_articles),
            2,
            "Portal should have been able to create 2 children",
        )

        article_favorites = self.env["knowledge.article.favorite"].search([])
        self.assertEqual(len(article_favorites), 2)
        self.assertEqual(article_favorites[0].article_id, private_article)
        self.assertEqual(article_favorites[1].article_id, workspace_article)

    def test_knowledge_pick_emoji(self):
        self.start_tour("/odoo", "knowledge_pick_emoji_tour", login="admin")

    def test_knowledge_cover_selector(self):
        with io.BytesIO() as f:
            Image.new("RGB", (50, 50)).save(f, "PNG")
            f.seek(0)
            image = base64.b64encode(f.read())
        attachment = self.env["ir.attachment"].create(
            {
                "name": "odoo_logo.png",
                "datas": image,
                "res_model": "knowledge.cover",
                "res_id": 0,
            }
        )
        self.env["knowledge.cover"].create({"attachment_id": attachment.id})
        self.start_tour("/odoo", "knowledge_cover_selector_tour", login="admin")

    def test_knowledge_readonly_favorite(self):
        articles = self.env["knowledge.article"].create(
            [
                {
                    "name": "Readonly Article 1",
                    "internal_permission": "read",
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.env.ref("base.partner_admin").id,
                                "permission": "write",
                            },
                        )
                    ],
                    "is_article_visible_by_everyone": True,
                },
                {
                    "name": "Readonly Article 2",
                    "internal_permission": False,
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.env.ref("base.partner_admin").id,
                                "permission": "write",
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "partner_id": self.partner_demo.id,
                                "permission": "read",
                            },
                        ),
                    ],
                    "is_article_visible_by_everyone": True,
                },
            ]
        )

        self.start_tour(
            "/knowledge/article/%s" % articles[0].id,
            "knowledge_readonly_favorite_tour",
            login="demo",
        )

        self.assertTrue(articles[0].with_user(self.user_demo.id).is_user_favorite)
        self.assertTrue(articles[1].with_user(self.user_demo.id).is_user_favorite)
        self.assertGreater(
            articles[0].with_user(self.user_demo.id).user_favorite_sequence,
            articles[1].with_user(self.user_demo.id).user_favorite_sequence,
        )

    def test_knowledge_resequence_children_of_readonly_parent_tour(self):
        parent = self.env["knowledge.article"].create(
            {
                "name": "Readonly Parent",
                "internal_permission": "read",
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.env.ref("base.partner_admin").id,
                            "permission": "write",
                        },
                    )
                ],
            }
        )
        self.env["knowledge.article"].create(
            [
                {
                    "name": "Child 1",
                    "internal_permission": "write",
                    "sequence": 1,
                    "parent_id": parent.id,
                },
                {
                    "name": "Child 2",
                    "internal_permission": "write",
                    "sequence": 2,
                    "parent_id": parent.id,
                },
            ]
        )
        self.start_tour(
            "/knowledge/article/%s" % parent.id,
            "knowledge_resequence_children_of_readonly_parent_tour",
            login="demo",
        )

    def test_knowledge_properties_tour(self):
        parent_article = self.env["knowledge.article"].create(
            [
                {
                    "name": "ParentArticle",
                    "sequence": 1,
                    "is_article_visible_by_everyone": True,
                },
                {
                    "name": "InheritPropertiesArticle",
                    "sequence": 2,
                    "is_article_visible_by_everyone": True,
                },
            ]
        )[0]
        self.env["knowledge.article"].create(
            {"name": "ChildArticle", "parent_id": parent_article.id}
        )
        self.start_tour("/odoo", "knowledge_properties_tour", login="admin")

    def test_knowledge_items_search_favorites_tour(self):
        self.env["knowledge.article"].create(
            [{"name": "Article 1", "is_article_visible_by_everyone": True}]
        )
        self.start_tour("/odoo", "knowledge_items_search_favorites_tour", login="admin")

    def test_knowledge_search_favorites_tour(self):
        self.env["knowledge.article"].create(
            [{"name": "Article 1", "is_article_visible_by_everyone": True}]
        )
        self.start_tour("/odoo", "knowledge_search_favorites_tour", login="admin")

    @users("admin")
    def test_knowledge_sidebar(self):
        self.start_tour("/odoo", "knowledge_sidebar_tour", login="admin", timeout=100)

        workspace_article = self.env["knowledge.article"].search(
            [("name", "=", "Workspace Article")]
        )
        self.assertTrue(bool(workspace_article))
        self.assertEqual(workspace_article.category, "workspace")
        self.assertFalse(workspace_article.parent_id)
        self.assertFalse(workspace_article.icon)

        workspace_child = self.env["knowledge.article"].search(
            [("name", "=", "Workspace Child")]
        )
        self.assertEqual(workspace_child.parent_id, workspace_article)
        self.assertFalse(workspace_child.icon)
        self.assertTrue(workspace_child.is_user_favorite)

        shared_article = (
            self.env["knowledge.article"]
            .with_context(active_test=False)
            .search([("name", "=", "Shared Article")])
        )
        self.assertTrue(bool(shared_article))
        self.assertEqual(shared_article.category, "shared")
        self.assertFalse(shared_article.active)

        private_article = self.env["knowledge.article"].search(
            [("name", "=", "Private Article")]
        )
        self.assertTrue(bool(private_article))
        self.assertEqual(private_article.category, "private")
        self.assertFalse(private_article.parent_id)
        self.assertGreater(
            private_article.user_favorite_sequence,
            workspace_child.user_favorite_sequence,
        )

        private_children = private_article.child_ids.sorted("sequence")
        self.assertEqual(private_children[0].name, "Private Child 3")
        self.assertTrue(private_children[0].icon)
        self.assertEqual(private_children[1].name, "Private Child 4")
        self.assertEqual(private_children[2].name, "Private Child 1")

        moved_to_share = (
            self.env["knowledge.article"]
            .with_context(active_test=False)
            .search([("name", "=", "Moved to Share")])
        )
        self.assertTrue(bool(moved_to_share))
        self.assertEqual(moved_to_share.parent_id, shared_article)
        self.assertEqual(moved_to_share.category, "shared")
        self.assertFalse(moved_to_share.active)

        private_child_2 = (
            self.env["knowledge.article"]
            .with_context(active_test=False)
            .search([("name", "=", "Private Child 2")])
        )
        self.assertTrue(bool(private_child_2))
        self.assertFalse(private_child_2.parent_id)
        self.assertGreater(private_child_2.sequence, private_article.sequence)
        self.assertFalse(private_child_2.active)

        private_article.write(
            {
                "internal_permission": "read",
                "is_article_visible_by_everyone": True,
                "sequence": workspace_article.sequence + 1,
            }
        )
        workspace_article.write(
            {
                "is_article_visible_by_everyone": True,
            }
        )
        self.start_tour("/odoo", "knowledge_sidebar_readonly_tour", login="demo")

        self.assertFalse(workspace_article.parent_id)
        self.assertGreater(private_article.sequence, workspace_article.sequence)


@tagged("external", "post_install", "-at_install")
@skipIf(
    not os.getenv("UNSPLASH_APP_ID") or not os.getenv("UNSPLASH_ACCESS_KEY"),
    "no unsplash credentials",
)
class TestKnowledgeUIWithUnsplash(TestKnowledgeUICommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.UNSPLASH_APP_ID = os.getenv("UNSPLASH_APP_ID")
        cls.UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

        cls.env["ir.config_parameter"].set_param("unsplash.app_id", cls.UNSPLASH_APP_ID)
        cls.env["credential.credential"]._set_system_secret(
            "unsplash.access_key", cls.UNSPLASH_ACCESS_KEY
        )

    def test_knowledge_cover_selector_unsplash(self):
        self.start_tour("/odoo", "knowledge_random_cover_tour", login="demo")
