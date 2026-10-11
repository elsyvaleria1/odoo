from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProductPublicCategory(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def create_multi(vals_list):
            return list(map(Command.create, vals_list))

        cls.published_product, cls.unpublished_product = cls.env[
            "product.template"
        ].create(
            [
                {"name": "Published Product", "is_published": True},
                {"name": "Unpublished Product", "is_published": False},
            ]
        )

        cls.env["product.public.category"].search([]).unlink()

        cls.env["product.public.category"].create(
            [
                {
                    "name": "1",
                    "child_id": create_multi(
                        [
                            {
                                "name": "1.1",
                                "child_id": create_multi([{"name": "1.1.1"}]),
                            },
                            {
                                "name": "1.2",
                                "product_tmpl_ids": [
                                    Command.link(cls.published_product.id)
                                ],
                            },
                        ]
                    ),
                },
                {
                    "name": "2",
                    "child_id": create_multi(
                        [
                            {
                                "name": "2.1",
                                "child_id": create_multi(
                                    [
                                        {
                                            "name": "2.1.1",
                                            "product_tmpl_ids": [
                                                Command.link(cls.published_product.id),
                                                Command.link(
                                                    cls.unpublished_product.id
                                                ),
                                            ],
                                        }
                                    ]
                                ),
                            },
                            {"name": "2.2"},
                        ]
                    ),
                },
                {
                    "name": "3",
                    "product_tmpl_ids": [Command.link(cls.unpublished_product.id)],
                },
            ]
        )

    def test_search_has_published_products(self):
        published_categs = set(
            self.env["product.public.category"]
            .search([("has_published_products", "not in", (False,))])
            .mapped("name")
        )

        self.assertSetEqual(published_categs, {"1", "1.2", "2", "2.1", "2.1.1"})

    def test_search_does_not_have_published_products(self):
        unpublished_categs = set(
            self.env["product.public.category"]
            .search([("has_published_products", "!=", True)])
            .mapped("name")
        )

        self.assertSetEqual(unpublished_categs, {"1.1", "1.1.1", "2.2", "3"})

    def test_compute_has_published_products_matches_the_search(self):
        categories = self.env["product.public.category"].search([])
        published = {
            category.name for category in categories if category.has_published_products
        }
        self.assertSetEqual(published, {"1", "1.2", "2", "2.1", "2.1.1"})

    def test_compute_has_published_products_reads_the_subtree_once(self):
        root = self.env["product.public.category"].search([("name", "=", "2")])
        self.env.invalidate_all()
        with self.capturedQueries() as queries:
            self.assertTrue(root.has_published_products)
        template_reads = [query for query in queries if '"product_template"' in query]
        self.assertEqual(
            len(template_reads),
            1,
            "a category's descendants are one grouped read, not one per level",
        )

    def test_an_archived_product_publishes_no_category(self):
        self.published_product.active = False
        published_categs = set(
            self.env["product.public.category"]
            .search([("has_published_products", "=", True)])
            .mapped("name")
        )
        self.assertSetEqual(published_categs, set())

    def test_search_has_published_products_is_one_query(self):
        public = self.env.ref("base.public_user")
        Category = self.env["product.public.category"].with_user(public)
        domain = [("has_published_products", "=", True)]
        Category.search_fetch(domain, ["name"])
        with self.capturedQueries() as queries:
            names = set(Category.search_fetch(domain, ["name"]).mapped("name"))
        self.assertSetEqual(names, {"1", "1.2", "2", "2.1", "2.1.1"})
        self.assertEqual(
            len(queries),
            1,
            "the condition and the public users' rule are subqueries of the search",
        )
