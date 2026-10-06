from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWebsiteArticleFlows(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.article = cls.env["knowledge.article"].create(
            {
                "name": "Public Yoga Handbook",
                "body": (
                    "<p>"
                    + "Yoga breathing techniques explained in detail. " * 5
                    + "</p><div data-embedded='view'>EMBEDDED</div>"
                ),
                "internal_permission": "write",
                "website_published": True,
            }
        )

    def test_search_articles_autocomplete(self):
        response = self.call_jsonrpc(
            "/website/snippet/autocomplete",
            {
                "search_type": "knowledge",
                "term": "Yoga",
                "max_nb_chars": 100,
                "options": {"displayDescription": True},
            },
        )
        self.assertGreaterEqual(response["results_count"], 1)
        names = [result["name"] for result in response["results"]]
        self.assertTrue(any("Yoga" in name and "Handbook" in name for name in names))

    def test_summary_excludes_embedded_and_truncates(self):
        self.assertNotIn("EMBEDDED", self.article.summary)
        self.assertTrue(self.article.summary.endswith("..."))
        self.assertLessEqual(len(self.article.summary), 110)

        empty = self.env["knowledge.article"].create(
            {"name": "Empty", "body": "<p><br/></p>", "internal_permission": "write"}
        )
        self.assertFalse(empty.summary)

    def test_website_bridges(self):
        self.assertEqual(self.article.website_url, self.article.article_url)
        self.assertEqual(
            self.article.get_backend_menu_id(),
            self.env.ref("knowledge.knowledge_menu_root").id,
        )
        domain = self.article._get_domain_read()
        self.assertIn(("website_published", "=", True), list(domain))
