from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install", "knowledge_article_stage")
class TestKnowledgeArticleStage(HttpCase):
    def test_compute_stage_id(self):
        article = self.env["knowledge.article"].create(
            {
                "name": "Parent Article",
            }
        )
        stages = self.env["knowledge.article.stage"].create(
            [
                {
                    "name": "Lost",
                    "sequence": 2,
                    "fold": True,
                    "parent_id": article.id,
                },
                {
                    "name": "Win",
                    "sequence": 1,
                    "parent_id": article.id,
                },
            ]
        )
        article_items = self.env["knowledge.article"].create(
            [
                {
                    "name": "Article Item 1",
                    "parent_id": article.id,
                    "is_article_item": True,
                },
                {
                    "name": "Article Item 2",
                    "parent_id": article.id,
                    "is_article_item": True,
                },
            ]
        )
        self.assertEqual(article_items[0].stage_id, stages[1])
        self.assertEqual(article_items[1].stage_id, stages[1])
