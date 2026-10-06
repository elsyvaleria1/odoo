from odoo.tests import users
from odoo.tests.common import tagged

from odoo.addons.knowledge.tests.common import KnowledgeCommonWData


@tagged("post_install", "-at_install")
class TestKnowledgePublishedPropagation(KnowledgeCommonWData):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grand_children_articles = cls.env["knowledge.article"].create(
            [
                {
                    "name": "Grand-Child Article 1",
                    "parent_id": cls.workspace_children[0].id,
                },
                {
                    "name": "Grand-Child Article 2",
                    "parent_id": cls.workspace_children[0].id,
                },
            ]
        )

    @users("employee")
    def test_knowledge_published_propagation(self):
        article = self.workspace_children[0].with_env(self.env)
        child_article = self.grand_children_articles[0].with_env(self.env)
        grandchild_article = self.env["knowledge.article"].create(
            {
                "name": "Grand-Child Article 3",
                "parent_id": child_article.id,
            }
        )

        article.write({"website_published": True})
        self.assertTrue(child_article.website_published)
        self.assertTrue(grandchild_article.website_published)

        newly_created_article = self.env["knowledge.article"].article_create(
            title="Newly Created Article", parent_id=grandchild_article.id
        )
        self.assertTrue(newly_created_article.website_published)

        newly_created_article.move_to(category="workspace")
        self.assertTrue(newly_created_article.website_published)
        newly_created_article.write({"website_published": False})

        newly_created_article.move_to(
            parent_id=child_article.id, before_article_id=grandchild_article.id
        )
        self.assertFalse(newly_created_article.website_published)

    @users("portal_test")
    def test_get_accessible_root_ancestor(self):
        article = self.article_workspace.with_env(self.env)
        child_article = self.workspace_children[0].with_env(self.env)
        grandchild_article = self.grand_children_articles[0].with_env(self.env)

        self.assertListEqual(
            grandchild_article._get_accessible_root_ancestors().ids, []
        )

        child_article.sudo().write({"website_published": True})
        self.assertListEqual(
            sorted(grandchild_article._get_accessible_root_ancestors().ids),
            sorted([child_article.id, grandchild_article.id]),
        )

        child_article.sudo().write({"website_published": False})

        article.sudo().invite_members(
            partners=self.env.user.partner_id, permission="read"
        )
        child_article.sudo().invite_members(
            partners=self.env.user.partner_id, permission="read"
        )
        grandchild_article.sudo().invite_members(
            partners=self.env.user.partner_id, permission="read"
        )

        self.assertListEqual(
            sorted(grandchild_article._get_accessible_root_ancestors().ids),
            sorted([article.id, child_article.id, grandchild_article.id]),
        )

        child_article.sudo().invite_members(
            partners=self.env.user.partner_id, permission="none"
        )

        self.assertListEqual(
            sorted(grandchild_article._get_accessible_root_ancestors().ids),
            [grandchild_article.id],
        )
        self.assertListEqual(
            sorted(child_article._get_accessible_root_ancestors().ids), []
        )
        self.assertListEqual(
            sorted(article._get_accessible_root_ancestors().ids), [article.id]
        )
