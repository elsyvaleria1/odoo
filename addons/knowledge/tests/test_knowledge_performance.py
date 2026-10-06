from odoo.tests.common import tagged, users, warmup
from odoo.tools import mute_logger

from odoo.addons.knowledge.tests.common import (
    KnowledgeArticlePermissionsCase,
    KnowledgeCommonWData,
)


@tagged("knowledge_performance", "post_install", "-at_install")
class KnowledgePerformanceCase(KnowledgeCommonWData):
    def setUp(self):
        super().setUp()
        # patch registry to simulate a ready environment
        self.patch(self.env.registry, "ready", True)
        # we don't use mock_mail_gateway thus want to mock smtp to test the stack
        self._mock_smtplib_connection()

    @users("admin")
    @warmup
    def test_article_copy_batch(self):
        """Test performance of batch-copying articles, which implies notably
        a descendants checks which might be costly.

        Done as admin as only admin has access to Duplicate button currently."""
        # +1: member.article_permission is read off the article, not off a copy
        # +11: the employees' permission is a grant row, apart from the article
        # +5: the copied tree's stored inherited label follows each parent it is given
        # +1: the template category is recursive over parent_id: the copies are
        # recomputed at flush, level by level, and read their parent's category
        with self.assertQueryCount(admin=61):
            workspace_children = self.workspace_children.with_env(self.env)
            shared = self.article_shared.with_env(self.env)
            _duplicates = (workspace_children + shared).copy_batch()
            self.assertEqual(len(_duplicates), 3)

    @users("employee")
    @warmup
    def test_article_creation_single_shared_grandchild(self):
        """Test with 2 levels of hierarchy in a private/shared environment"""
        # +1: the message posted on create reads the company's mail.config row
        # +2: the employees' permission is a grant row, apart from the article
        with self.assertQueryCount(employee=22):
            _article = self.env["knowledge.article"].create(
                {
                    "body": "<p>Hello</p>",
                    "name": "Article in shared",
                    "parent_id": self.shared_children[0].id,
                }
            )

        self.assertEqual(_article.category, "shared")

    @users("employee")
    @warmup
    def test_article_creation_single_workspace(self):
        # +1: the message posted on create reads the company's mail.config row
        # +3: the employees' permission is a grant row, apart from the article
        with self.assertQueryCount(employee=21):
            _article = self.env["knowledge.article"].create(
                {
                    "body": "<p>Hello</p>",
                    "name": "Article in workspace",
                    "parent_id": self.article_workspace.id,
                }
            )

        self.assertEqual(_article.category, "workspace")

    @users("employee")
    @warmup
    def test_article_creation_multi_roots(self):
        # +1: the message posted on create reads the company's mail.config row
        # +6: the employees' permission is a grant row, apart from the article
        # +1: the label guard reads a node's stored label before the rule's SQL
        with self.assertQueryCount(employee=22):
            _article = self.env["knowledge.article"].create(
                [
                    {
                        "body": "<p>Hello</p>",
                        "internal_permission": "write",
                        "name": f"Article {index} in workspace",
                    }
                    for index in range(10)
                ]
            )

    @users("employee")
    @warmup
    def test_article_creation_multi_shared_grandchild(self):
        # +1: the message posted on create reads the company's mail.config row
        # +2: the employees' permission is a grant row, apart from the article
        with self.assertQueryCount(employee=22):
            _article = self.env["knowledge.article"].create(
                [
                    {
                        "body": "<p>Hello</p>",
                        "name": f"Article {index} in workspace",
                        "parent_id": self.shared_children[0].id,
                    }
                    for index in range(10)
                ]
            )

    @users("employee")
    @warmup
    def test_article_favorite(self):
        with self.assertQueryCount(employee=12):
            shared_article = self.shared_children[0].with_env(self.env)
            shared_article.action_toggle_user_favorite()

    @users("employee")
    @warmup
    def test_article_get_valid_parent_options(self):
        with self.assertQueryCount(employee=3):
            child_writable_article = self.workspace_children[1].with_env(self.env)
            # don't check actual results, those are tested in ``TestKnowledgeArticleUtilities`` class
            _res = child_writable_article.get_valid_parent_options(search_term="")

    @users("employee")
    @warmup
    def test_article_home_page(self):
        # +1: the employees' permission is a grant row, apart from the article
        with self.assertQueryCount(employee=10):
            self.env["knowledge.article"].action_home_page()

    @mute_logger(
        "odoo.addons.base.models.ir_access",
        "odoo.addons.mail.models.mail_mail",
        "odoo.models.unlink",
        "odoo.tests",
    )
    @users("employee")
    @warmup
    def test_article_invite_members(self):
        # +1: member.article_permission is read off the article, not off a copy
        # +5: the employees' permission is a grant row, apart from the article
        # +5: the invitation link issued to the share partner invited
        with self.assertQueryCount(employee=72):
            shared_article = self.shared_children[0].with_env(self.env)
            partners = (
                self.customer + self.partner_employee_manager + self.partner_employee2
            ).with_env(self.env)
            shared_article.invite_members(partners, "write")

    @users("employee")
    @warmup
    def test_article_move_to(self):
        before_id = self.workspace_children[0].id
        # +3: the employees' permission is a grant row, apart from the article
        # +1 with website_helpdesk_knowledge: setting a parent first asks whether
        # a helpdesk team uses the article as its help center, which it refuses
        team_guard = (
            "team.team" in self.env
            and "website_article_id" in self.env["team.team"]._fields
        )
        with self.assertQueryCount(employee=17 + team_guard):
            writable_article = self.workspace_children[1].with_env(self.env)
            writable_article.move_to(
                parent_id=writable_article.parent_id.id, before_article_id=before_id
            )

    @users("employee")
    @warmup
    def test_get_user_sorted_articles(self):
        # +1: the employees' permission is a grant row, apart from the article
        with self.assertQueryCount(employee=2):
            self.env["knowledge.article"].get_user_sorted_articles("")


@tagged("knowledge_performance", "post_install", "-at_install")
class KnowledgePerformancePermissionCase(KnowledgeArticlePermissionsCase):
    def setUp(self):
        super().setUp()
        # patch registry to simulate a ready environment
        self.patch(self.env.registry, "ready", True)
        # we don't use mock_mail_gateway thus want to mock smtp to test the stack
        self._mock_smtplib_connection()

    @users("employee")
    @warmup
    def test_user_has_parent_path_access(self):
        """We are testing the performance to access the field user_has_parent_path_access in different situations.
        The arborescence tested here is the one contained inside Readable Root.
        """
        self.assertFalse(self.article_read_contents_children.user_has_access)

        self.article_read_contents_children.sudo()._add_members(
            self.env.user.partner_id, "read"
        )
        self.assertTrue(
            self.article_read_contents_children.with_user(self.env.user).user_has_access
        )

        # Testing the number of queries depending on the number of ancestors => parent_path
        # Conclusion: No evolution with a higher number of ancestors
        # article_headers[1] => ('TTRPG')
        with self.assertQueryCount(employee=2):
            _ = (
                self.article_headers[1]
                .with_user(self.env.user)
                .user_has_access_parent_path
            )

        # article_read_contents_children => (Child of 'Secret')
        with self.assertQueryCount(employee=1):
            _ = self.article_read_contents_children.with_user(
                self.env.user
            ).user_has_access_parent_path
        # article_read_desync => (Child of 'Mansion of Terror')
        with self.assertQueryCount(employee=2):
            _ = (
                self.article_read_desync[0]
                .with_user(self.env.user)
                .user_has_access_parent_path
            )

        # Testing evolution in query number depending on the number of tested records
        # Conclusion: Proportional evolution
        # article_read_contents[0] => ('OpenCthulhu')
        with self.assertQueryCount(employee=1):
            _ = (
                self.article_read_contents[0]
                .with_user(self.env.user)
                .user_has_access_parent_path
            )

        # article_read_contents[1:3] => ('Open Paranoïa'), ('Proprietary RPGs')
        with self.assertQueryCount(employee=0):
            for article in self.article_read_contents[1:3]:
                _ = article.with_user(self.env.user).user_has_access_parent_path


@tagged("knowledge_performance", "post_install", "-at_install")
class KnowledgePerformanceSidebarCase(KnowledgeCommonWData):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.wkspace_grand_children = cls.env["knowledge.article"].create(
            [
                {
                    "name": "Workspace Grand-Child",
                    "parent_id": cls.workspace_children[0].id,
                }
            ]
            * 2
        )

    def setUp(self):
        super().setUp()
        # patch registry to simulate a ready environment
        self.patch(self.env.registry, "ready", True)
        # we don't use mock_mail_gateway thus want to mock smtp to test the stack
        self._mock_smtplib_connection()
        # +1 with website_knowledge: a published article is readable by anyone,
        # and has_access on the root article evaluates that leaf in memory,
        # which fetches the root before the SQL check of the rest
        self.published_leaf = (
            "website_published" in self.env["knowledge.article"]._fields
        )

    @users("employee")
    @warmup
    def test_article_tree_panel(self):
        # +1: the label guard reads a node's stored label before the rule's SQL
        with self.assertQueryCount(employee=12 + self.published_leaf):
            self.wkspace_grand_children[0].with_user(
                self.env.user.id
            ).get_sidebar_articles([self.article_shared.id])

    @users("employee")
    @warmup
    def test_article_tree_panel_w_favorites(self):
        self.env["knowledge.article.favorite"].create(
            [
                {"user_id": self.env.user.id, "article_id": article_id}
                for article_id in (
                    self.workspace_children | self.wkspace_grand_children
                ).ids
            ]
        )

        # +1: favorite.is_article_active is read off the article, not off a copy
        # +1: the label guard reads a node's stored label before the rule's SQL
        with self.assertQueryCount(employee=12 + self.published_leaf):
            self.wkspace_grand_children[0].with_user(
                self.env.user.id
            ).get_sidebar_articles([self.article_shared.id])
