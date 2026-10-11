from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSlideSearch(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["slide.channel"].create(
            {"name": "Searchable Zebra course", "is_published": True}
        )
        cls.env["slide.slide"].create(
            [
                {
                    "name": "Zebra section",
                    "channel_id": cls.channel.id,
                    "is_category": True,
                },
                {
                    "name": "Zebra lesson",
                    "channel_id": cls.channel.id,
                    "slide_category": "article",
                    "html_content": "<p>x</p>",
                    "is_published": True,
                    "is_preview": True,
                },
                {
                    "name": "Zebra draft",
                    "channel_id": cls.channel.id,
                    "slide_category": "article",
                    "html_content": "<p>x</p>",
                },
            ]
        )

    def _autocomplete(self, search_type):
        result = self.call_jsonrpc(
            "/website/snippet/autocomplete",
            {
                "search_type": search_type,
                "term": "Zebra",
                "order": "name asc",
                "limit": 10,
                "options": {
                    "displayImage": True,
                    "displayDescription": True,
                    "displayExtraLink": True,
                    "displayDetail": False,
                    "allowFuzzy": True,
                    "order": "name asc",
                    "my": "0",
                    "prevent_redirect": "True",
                },
            },
        )
        return sorted(row["_fa"] for row in result["results"])

    def test_the_courses_search_box_finds_courses_and_lessons(self):
        self.assertEqual(
            self._autocomplete("slides"),
            ["fa-graduation-cap", "fa-regular fa-file-lines"],
        )

    def test_a_lesson_search_leaves_out_sections_and_drafts(self):
        self.assertEqual(
            self._autocomplete("slides_only"), ["fa-regular fa-file-lines"]
        )
