from urllib.parse import parse_qs, urlsplit

from lxml import html

from odoo import http
from odoo.fields import Datetime
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestCourseJoinForm(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.learner = new_test_user(
            cls.env, login="course_learner", groups="base.group_portal"
        )
        cls.channel = cls.env["slide.channel"].create(
            {
                "name": "Joinable course",
                "enroll": "public",
                "is_published": True,
                "slide_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Joinable lesson",
                            "slide_category": "article",
                            "html_content": "<p>Read me</p>",
                            "is_published": True,
                        },
                    )
                ],
            }
        )

    def _join(self, channel_id=None, redirect="/slides/x?y=1"):
        return self.url_open(
            f"/slides/channel/{channel_id or self.channel.id}/join",
            data={"csrf_token": http.Request.csrf_token(self), "redirect": redirect},
            allow_redirects=False,
        )

    def _page(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200, response.text)
        self.shown_path = urlsplit(response.url).path
        return html.fromstring(response.content)

    def test_a_signed_in_user_joins_and_comes_back_to_the_page(self):
        self.authenticate("course_learner", "course_learner")

        response = self._join()

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/slides/x?y=1"))
        self.assertIn(self.learner.partner_id, self.channel.partner_ids)

    def test_a_visitor_is_sent_to_log_in_and_back(self):
        self.authenticate(None, None)

        response = self._join()

        self.assertEqual(response.status_code, 303)
        location = urlsplit(response.headers["Location"])
        self.assertEqual(location.path, "/web/login")
        self.assertEqual(parse_qs(location.query)["redirect"], ["/slides/x?y=1"])
        self.assertFalse(self.channel.partner_ids)

    def test_an_invited_user_joins_an_invitation_only_course(self):
        self.channel.enroll = "invite"
        self.env["slide.channel.partner"].create(
            {
                "channel_id": self.channel.id,
                "partner_id": self.learner.partner_id.id,
                "member_status": "invited",
                "last_invitation_date": Datetime.now(),
            }
        )
        self.authenticate("course_learner", "course_learner")

        self._join()

        self.assertIn(self.learner.partner_id, self.channel.partner_ids)

    def test_a_user_not_invited_comes_back_to_the_page_not_joined(self):
        self.channel.enroll = "invite"
        self.authenticate("course_learner", "course_learner")

        response = self._join()

        self.assertEqual(response.status_code, 303)
        self.assertNotIn(self.learner.partner_id, self.channel.partner_ids)

    def test_an_unknown_course_is_not_found(self):
        self.authenticate("course_learner", "course_learner")

        self.assertEqual(self._join(channel_id=self.channel.id + 1000).status_code, 404)

    def test_the_course_page_offers_joining_as_a_form_of_its_own(self):
        self.authenticate("course_learner", "course_learner")

        page = self._page(f"/slides/{self.channel.id}")

        (button,) = page.xpath(
            "//button[contains(@class, 'o_wslides_course_join_button')]"
        )
        form = button.xpath("ancestor::form")[0]
        self.assertEqual(form.get("method"), "post")
        self.assertEqual(form.get("action"), f"/slides/channel/{self.channel.id}/join")
        self.assertEqual(
            form.xpath("input[@name='redirect']/@value"), [self.shown_path]
        )
        self.assertFalse(page.xpath("//form//form"))

    def test_the_invitation_preview_sends_the_visitor_to_identify(self):
        self.channel.visibility = "members"
        channel_partner = self.env["slide.channel.partner"].create(
            {
                "channel_id": self.channel.id,
                "partner_id": self.learner.partner_id.id,
                "member_status": "invited",
                "last_invitation_date": Datetime.now(),
            }
        )
        channel_partner._issue_invitation_links()
        self.authenticate(None, None)

        page = self._page(channel_partner.invitation_link)

        (link,) = page.xpath("//a[contains(@class, 'o_wslides_course_join_button')]")
        href = urlsplit(link.get("href"))
        self.assertEqual(href.path, f"/slides/{self.channel.id}/identify")
        self.assertEqual(
            set(parse_qs(href.query)), {"invite_partner_id", "invite_hash"}
        )
        self.assertFalse(
            page.xpath(f"//form[@action='/slides/channel/{self.channel.id}/join']")
        )

    def test_a_lesson_s_join_link_is_a_form_back_to_the_lesson(self):
        slide = self.channel.slide_ids
        slide.write(
            {
                "is_preview": True,
                "slide_resource_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Notes",
                            "resource_type": "url",
                            "link": "https://example.com",
                        },
                    )
                ],
            }
        )
        self.authenticate("course_learner", "course_learner")

        page = self._page(f"/slides/slide/{slide.id}")

        forms = page.xpath(
            f"//form[@action='/slides/channel/{self.channel.id}/join']"
            "[.//button[contains(@class, 'o_wslides_course_join_button')]]"
        )
        self.assertTrue(forms)
        self.assertFalse(page.xpath("//form//form"))

    def test_the_fullscreen_player_s_join_form_comes_back_to_its_lesson(self):
        preview = self.channel.slide_ids
        preview.is_preview = True
        locked = self.env["slide.slide"].create(
            {
                "name": "Locked lesson",
                "channel_id": self.channel.id,
                "slide_category": "article",
                "html_content": "<p>Members only</p>",
                "is_published": True,
                "slide_resource_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Notes",
                            "resource_type": "url",
                            "link": "https://example.com",
                        },
                    )
                ],
            }
        )
        self.authenticate("course_learner", "course_learner")

        page = self._page(f"/slides/slide/{preview.id}?fullscreen=1")

        (form,) = page.xpath(
            f"//form[@action='/slides/channel/{self.channel.id}/join']"
        )
        redirect = form.xpath("input[@name='redirect']/@value")[0]
        self.assertTrue(redirect.startswith("/slides/slide/"), redirect)
        self.assertTrue(redirect.endswith(f"-{locked.id}?fullscreen=1"), redirect)
        self.assertFalse(page.xpath("//form//form"))

    def test_a_preview_lesson_opens_beside_a_locked_one_with_resources(self):
        # QWeb evaluates t-foreach before t-if: a guard on the loop's own node
        # read the locked lesson's resources as the visitor, and the page 403d
        preview = self.channel.slide_ids
        preview.is_preview = True
        self.env["slide.slide"].create(
            {
                "name": "Locked lesson",
                "channel_id": self.channel.id,
                "slide_category": "article",
                "html_content": "<p>Members only</p>",
                "is_published": True,
                "slide_resource_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Notes",
                            "resource_type": "url",
                            "link": "https://example.com",
                        },
                    )
                ],
            }
        )
        self.authenticate("course_learner", "course_learner")

        for url in (
            f"/slides/slide/{preview.id}",
            f"/slides/slide/{preview.id}?fullscreen=1",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.url_open(url).status_code, 200)

    def test_a_documentation_lesson_offers_starting_the_course_as_a_form(self):
        self.channel.channel_type = "documentation"
        lesson = self.channel.slide_ids
        lesson.is_preview = True
        self.authenticate("course_learner", "course_learner")

        page = self._page(f"/slides/slide/{lesson.id}")

        (form,) = page.xpath(
            f"//form[@action='/slides/channel/{self.channel.id}/join']"
            "[.//button[contains(., 'Start this Course')]]"
        )
        self.assertEqual(
            form.xpath("input[@name='redirect']/@value"), [self.shown_path]
        )
        self.assertFalse(page.xpath("//form//form"))
