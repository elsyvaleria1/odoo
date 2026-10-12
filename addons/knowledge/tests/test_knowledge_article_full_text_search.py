from markupsafe import Markup

from odoo.tests.common import users
from odoo.tools import mute_logger

from odoo.addons.knowledge.tests.common import KnowledgeCommon


class TestKnowledgeArticleFullTextSearch(KnowledgeCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        Article = cls.env["knowledge.article"]
        with mute_logger("odoo.models.unlink"):
            Article.search([]).unlink()

        cls.workspace_article_visible = Article.create(
            {
                "name": "10 unknown facts about Pim's",
                "internal_permission": "write",
                "is_article_visible_by_everyone": True,
                "favorite_ids": [(0, 0, {"user_id": cls.user_admin.id})],
                "body": Markup(
                    "<p>Pim's are circular in shape, making them easier to eat.</p>"
                ),
            }
        )
        cls.workspace_child_article_visible = Article.create(
            {
                "name": "Ingredients",
                "internal_permission": "write",
                "is_article_visible_by_everyone": True,
                "favorite_ids": [(0, 0, {"user_id": cls.user_employee.id})],
                "parent_id": cls.workspace_article_visible.id,
                "body": Markup(
                    "<p>Most Pim's are made with biscuit, marmalade and chocolate.</p>"
                ),
            }
        )
        cls.workspace_article_hidden = Article.create(
            {
                "name": "HR",
                "internal_permission": "write",
                "body": Markup("<p>The company has 50 amazing employees</p>"),
            }
        )
        cls.workspace_child_article_hidden = Article.create(
            {
                "name": "Recruitment",
                "internal_permission": "write",
                "parent_id": cls.workspace_article_hidden.id,
                "body": Markup(
                    "<p>That's amazing! We hired 3 new employees this semester</p>"
                ),
            }
        )

        cls.shared_article = Article.create(
            {
                "name": "TODO list",
                "internal_permission": "none",
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.user_admin.partner_id.id,
                            "permission": "write",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.user_employee.partner_id.id,
                            "permission": "write",
                        },
                    ),
                ],
                "body": Markup("<p>Purchase Pim's</p>"),
            }
        )

        cls.private_article_admin = Article.create(
            {
                "name": "My favorite Pim's flavors",
                "internal_permission": "none",
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.user_admin.partner_id.id,
                            "permission": "write",
                        },
                    )
                ],
                "body": Markup("<p>Orange, Raspberry, etc.</p>"),
            }
        )
        cls.private_article_user = Article.create(
            {
                "name": "Secret Luc's birthday party",
                "internal_permission": "none",
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.user_employee.partner_id.id,
                            "permission": "write",
                        },
                    )
                ],
                "body": Markup("<p>Don't forget to bring some Pim's!</p>"),
            }
        )

    @users("admin")
    def test_get_user_sorted_articles_admin(self):
        test_dataset = [
            (
                "",
                False,
                [
                    {
                        "id": self.workspace_article_visible.id,
                        "icon": False,
                        "name": "10 unknown facts about Pim's",
                        "is_user_favorite": True,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "10 unknown facts about Pim's",
                False,
                [
                    {
                        "id": self.workspace_article_visible.id,
                        "icon": False,
                        "name": "10 unknown facts about Pim's",
                        "is_user_favorite": True,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "shape",
                False,
                [
                    {
                        "id": self.workspace_article_visible.id,
                        "icon": False,
                        "name": "10 unknown facts about Pim's",
                        "headline": "circular in <strong>shape</strong>, making them easier",
                        "is_user_favorite": True,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "Ingredients",
                False,
                [
                    {
                        "id": self.workspace_child_article_visible.id,
                        "icon": False,
                        "name": "Ingredients",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "biscuit marmalade chocolate",
                False,
                [
                    {
                        "id": self.workspace_child_article_visible.id,
                        "icon": False,
                        "name": "Ingredients",
                        "headline": "Most Pim's are made with <strong>biscuit</strong>, <strong>marmalade</strong> and <strong>chocolate</strong>",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            ("HR", False, []),
            (
                "HR",
                True,
                [
                    {
                        "id": self.workspace_article_hidden.id,
                        "icon": False,
                        "name": "HR",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            ("company", False, []),
            (
                "company",
                True,
                [
                    {
                        "id": self.workspace_article_hidden.id,
                        "icon": False,
                        "name": "HR",
                        "headline": "<strong>company</strong> has 50 amazing employees",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            ("Recruitment", False, []),
            (
                "Recruitment",
                True,
                [
                    {
                        "id": self.workspace_child_article_hidden.id,
                        "icon": False,
                        "name": "Recruitment",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            ("semester", False, []),
            (
                "semester",
                True,
                [
                    {
                        "id": self.workspace_child_article_hidden.id,
                        "icon": False,
                        "name": "Recruitment",
                        "headline": "That's amazing! We hired 3 new employees this <strong>semester</strong>",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            (
                "TODO list",
                False,
                [
                    {
                        "id": self.shared_article.id,
                        "icon": False,
                        "name": "TODO list",
                        "is_user_favorite": False,
                        "root_article_id": (self.shared_article.id, "📄 TODO list"),
                    }
                ],
            ),
            (
                "Purchase Pim's",
                False,
                [
                    {
                        "id": self.shared_article.id,
                        "icon": False,
                        "name": "TODO list",
                        "headline": "<strong>Purchase</strong> <strong>Pim</strong>'<strong>s</strong>",
                        "is_user_favorite": False,
                        "root_article_id": (self.shared_article.id, "📄 TODO list"),
                    }
                ],
            ),
            (
                "My favorite Pim's flavors",
                False,
                [
                    {
                        "id": self.private_article_admin.id,
                        "icon": False,
                        "name": "My favorite Pim's flavors",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.private_article_admin.id,
                            "📄 My favorite Pim's flavors",
                        ),
                    }
                ],
            ),
            (
                "Orange",
                False,
                [
                    {
                        "id": self.private_article_admin.id,
                        "icon": False,
                        "name": "My favorite Pim's flavors",
                        "headline": "<strong>Orange</strong>, Raspberry",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.private_article_admin.id,
                            "📄 My favorite Pim's flavors",
                        ),
                    }
                ],
            ),
            ("Secret Luc's birthday party", False, []),
            ("forget", False, []),
        ]

        Article = self.env["knowledge.article"]
        for search_term, hidden_mode, expected_result in test_dataset:
            with self.subTest(search_term=search_term):
                self.assertEqual(
                    Article.get_user_sorted_articles(
                        search_term, hidden_mode=hidden_mode
                    ),
                    expected_result,
                    msg=f'search_term="{search_term}"',
                )

    @users("employee")
    def test_get_user_sorted_articles_user(self):
        test_dataset = [
            (
                "",
                False,
                [
                    {
                        "id": self.workspace_child_article_visible.id,
                        "icon": False,
                        "name": "Ingredients",
                        "is_user_favorite": True,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "10 unknown facts about Pim's",
                False,
                [
                    {
                        "id": self.workspace_article_visible.id,
                        "icon": False,
                        "name": "10 unknown facts about Pim's",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "shape",
                False,
                [
                    {
                        "id": self.workspace_article_visible.id,
                        "icon": False,
                        "name": "10 unknown facts about Pim's",
                        "headline": "circular in <strong>shape</strong>, making them easier",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "Ingredients",
                False,
                [
                    {
                        "id": self.workspace_child_article_visible.id,
                        "icon": False,
                        "name": "Ingredients",
                        "is_user_favorite": True,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            (
                "biscuit marmalade chocolate",
                False,
                [
                    {
                        "id": self.workspace_child_article_visible.id,
                        "icon": False,
                        "name": "Ingredients",
                        "headline": "Most Pim's are made with <strong>biscuit</strong>, <strong>marmalade</strong> and <strong>chocolate</strong>",
                        "is_user_favorite": True,
                        "root_article_id": (
                            self.workspace_article_visible.id,
                            "📄 10 unknown facts about Pim's",
                        ),
                    }
                ],
            ),
            ("HR", False, []),
            (
                "HR",
                True,
                [
                    {
                        "id": self.workspace_article_hidden.id,
                        "icon": False,
                        "name": "HR",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            ("company", False, []),
            (
                "company",
                True,
                [
                    {
                        "id": self.workspace_article_hidden.id,
                        "icon": False,
                        "name": "HR",
                        "headline": "<strong>company</strong> has 50 amazing employees",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            ("Recruitment", False, []),
            (
                "Recruitment",
                True,
                [
                    {
                        "id": self.workspace_child_article_hidden.id,
                        "icon": False,
                        "name": "Recruitment",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            ("semester", False, []),
            (
                "semester",
                True,
                [
                    {
                        "id": self.workspace_child_article_hidden.id,
                        "icon": False,
                        "name": "Recruitment",
                        "headline": "That's amazing! We hired 3 new employees this <strong>semester</strong>",
                        "is_user_favorite": False,
                        "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                    }
                ],
            ),
            (
                "TODO list",
                False,
                [
                    {
                        "id": self.shared_article.id,
                        "icon": False,
                        "name": "TODO list",
                        "is_user_favorite": False,
                        "root_article_id": (self.shared_article.id, "📄 TODO list"),
                    }
                ],
            ),
            (
                "Purchase Pim's",
                False,
                [
                    {
                        "id": self.shared_article.id,
                        "icon": False,
                        "name": "TODO list",
                        "headline": "<strong>Purchase</strong> <strong>Pim</strong>'<strong>s</strong>",
                        "is_user_favorite": False,
                        "root_article_id": (self.shared_article.id, "📄 TODO list"),
                    }
                ],
            ),
            ("My favorite Pim's flavors", False, []),
            ("Gift", False, []),
            (
                "Secret Luc's birthday party",
                False,
                [
                    {
                        "id": self.private_article_user.id,
                        "icon": False,
                        "name": "Secret Luc's birthday party",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.private_article_user.id,
                            "📄 Secret Luc's birthday party",
                        ),
                    }
                ],
            ),
            (
                "forget",
                False,
                [
                    {
                        "id": self.private_article_user.id,
                        "icon": False,
                        "name": "Secret Luc's birthday party",
                        "headline": "<strong>forget</strong> to bring some",
                        "is_user_favorite": False,
                        "root_article_id": (
                            self.private_article_user.id,
                            "📄 Secret Luc's birthday party",
                        ),
                    }
                ],
            ),
        ]

        Article = self.env["knowledge.article"]
        for search_term, hidden_mode, expected_result in test_dataset:
            with self.subTest(search_term=search_term):
                self.assertEqual(
                    Article.get_user_sorted_articles(
                        search_term, hidden_mode=hidden_mode
                    ),
                    expected_result,
                    msg=f'search_term="{search_term}"',
                )

    @users("admin")
    def test_get_user_sorted_ordering(self):
        Article = self.env["knowledge.article"]
        self.assertEqual(
            Article.get_user_sorted_articles("Pim's", hidden_mode=False),
            [
                {
                    "id": self.workspace_article_visible.id,
                    "icon": False,
                    "name": "10 unknown facts about Pim's",
                    "headline": "<strong>Pim</strong>'<strong>s</strong> are circular in shape, making them easier",
                    "is_user_favorite": True,
                    "root_article_id": (
                        self.workspace_article_visible.id,
                        "📄 10 unknown facts about Pim's",
                    ),
                },
                {
                    "id": self.private_article_admin.id,
                    "icon": False,
                    "name": "My favorite Pim's flavors",
                    "is_user_favorite": False,
                    "root_article_id": (
                        self.private_article_admin.id,
                        "📄 My favorite Pim's flavors",
                    ),
                },
                {
                    "id": self.shared_article.id,
                    "icon": False,
                    "name": "TODO list",
                    "headline": "Purchase <strong>Pim</strong>'<strong>s</strong>",
                    "is_user_favorite": False,
                    "root_article_id": (self.shared_article.id, "📄 TODO list"),
                },
                {
                    "id": self.workspace_child_article_visible.id,
                    "icon": False,
                    "name": "Ingredients",
                    "headline": "Most <strong>Pim</strong>'<strong>s</strong> are made with biscuit, marmalade and chocolate",
                    "is_user_favorite": False,
                    "root_article_id": (
                        self.workspace_article_visible.id,
                        "📄 10 unknown facts about Pim's",
                    ),
                },
            ],
        )

        self.assertEqual(
            Article.get_user_sorted_articles("amazing employees", hidden_mode=True),
            [
                {
                    "id": self.workspace_article_hidden.id,
                    "icon": False,
                    "name": "HR",
                    "headline": "company has 50 <strong>amazing</strong> <strong>employees</strong>",
                    "is_user_favorite": False,
                    "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                },
                {
                    "id": self.workspace_child_article_hidden.id,
                    "icon": False,
                    "name": "Recruitment",
                    "headline": "That's <strong>amazing</strong>! We hired 3 new <strong>employees</strong> this semester",
                    "is_user_favorite": False,
                    "root_article_id": (self.workspace_article_hidden.id, "📄 HR"),
                },
            ],
        )
