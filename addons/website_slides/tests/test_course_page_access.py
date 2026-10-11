from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCoursePageAccess(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["slide.channel"].create(
            {
                "name": "Public documentation",
                "channel_type": "documentation",
                "visibility": "public",
                "enroll": "public",
                "is_published": True,
            }
        )
        cls.tag = cls.env["slide.tag"].create({"name": "Locked lesson tag"})
        cls.category, cls.locked = cls.env["slide.slide"].create(
            [
                {
                    "name": "Section",
                    "channel_id": cls.channel.id,
                    "is_category": True,
                    "sequence": 1,
                },
                {
                    "name": "Members-only lesson",
                    "channel_id": cls.channel.id,
                    "slide_category": "article",
                    "html_content": "<p>locked</p>",
                    "is_published": True,
                    "tag_ids": [cls.tag.id],
                    "sequence": 2,
                },
            ]
        )

    def test_a_visitor_sees_a_documentation_course_beside_its_locked_lessons(self):
        response = self.url_open(f"/slides/{self.channel.id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Members-only lesson", response.text)
        self.assertIn("Locked lesson tag", response.text)

    def test_a_malformed_number_in_the_query_is_ignored(self):
        for query in (
            "invite_partner_id=abc&invite_hash=x",
            "access_error=course_content&access_error_slide_id=abc",
        ):
            with self.subTest(query=query):
                response = self.url_open(f"/slides/{self.channel.id}?{query}")
                self.assertEqual(response.status_code, 200)

    def test_a_malformed_invitation_partner_is_an_invitation_error(self):
        response = self.url_open(
            f"/slides/{self.channel.id}/invite?invite_partner_id=abc&invite_hash=x",
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertNotIn("invite_error", response.headers["Location"])
