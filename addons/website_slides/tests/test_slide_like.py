import re

from odoo import http
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER


@tagged("post_install", "-at_install")
class TestSlideLike(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.voter = new_test_user(
            cls.env, login="slide_voter", groups="base.group_portal", karma=1000
        )
        cls.channel = cls.env["slide.channel"].create(
            {
                "name": "Likeable course",
                "enroll": "public",
                "allow_comment": True,
                "is_published": True,
                "slide_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Likeable lesson",
                            "slide_category": "article",
                            "html_content": "<p>Read me</p>",
                            "is_published": True,
                        },
                    )
                ],
            }
        )
        cls.slide = cls.channel.slide_ids

    def _like(self, upvote="1", headers=None):
        return self.url_open(
            "/slides/slide/like",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "slide_id": self.slide.id,
                "upvote": upvote,
                "redirect": "/slides/x?y=1",
            },
            headers=headers,
            allow_redirects=False,
        )

    def test_a_member_s_like_answers_its_own_widget(self):
        self.channel._action_add_members(self.voter.partner_id)
        self.authenticate("slide_voter", "slide_voter")

        response = self._like(headers={FRAGMENTS_HEADER: "1"})

        self.assertEqual(response.status_code, 200, response.text)
        (fragment,) = response.json()["fragments"]
        self.assertEqual(fragment["key"], f"website_slides.slide_like.{self.slide.id}")
        self.assertIn("fa-solid fa-thumbs-up", fragment["html"])
        self.assertIn('value="/slides/x?y=1"', fragment["html"])
        self.assertEqual(self.slide.likes, 1)

    def test_a_like_without_javascript_returns_to_the_page(self):
        self.channel._action_add_members(self.voter.partner_id)
        self.authenticate("slide_voter", "slide_voter")

        response = self._like(upvote="0")

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/slides/x?y=1"))
        self.assertEqual(self.slide.dislikes, 1)

    def test_a_visitor_is_sent_to_log_in(self):
        self.authenticate(None, None)

        response = self._like(headers={FRAGMENTS_HEADER: "1"})

        self.assertEqual(response.status_code, 303)
        location = self.parse_http_location(response.headers["Location"])
        self.assertEqual(location.path, "/web/login")
        self.assertIn("redirect=%2Fslides%2Fx%3Fy%3D1", location.query)
        self.assertEqual(self.slide.likes, 0)

    def test_a_non_member_is_refused_in_place(self):
        self.slide.is_preview = True
        self.authenticate("slide_voter", "slide_voter")

        response = self._like(headers={FRAGMENTS_HEADER: "1"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["message"],
            "You must be member of this course to vote",
        )
        self.assertEqual(self.slide.likes, 0)

    def test_a_like_swaps_in_place(self):
        self.channel._action_add_members(self.voter.partner_id)

        self.start_tour(
            self.slide.website_url, "slide_like_in_place", login="slide_voter"
        )

        self.assertEqual(self.slide.likes, 1)

    def test_the_course_page_nests_no_form_in_another(self):
        self.channel.channel_type = "documentation"
        self.channel._action_add_members(self.voter.partner_id)
        self.authenticate("slide_voter", "slide_voter")

        page = self.url_open(self.channel.website_url).text

        self.assertIn(f"website_slides.slide_like.{self.slide.id}", page)
        depth = 0
        for tag in re.findall(r"<(/?)form\b", page):
            depth += -1 if tag else 1
            self.assertLessEqual(depth, 1, "a form is opened inside another")
