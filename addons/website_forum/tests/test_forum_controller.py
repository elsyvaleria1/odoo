from lxml import html

from odoo import http
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.website_forum.controllers.website_forum import WebsiteForum
from odoo.addons.website_forum.tests.common import KARMA, TestForumCommon


class TestForumController(TestForumCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._activate_multi_website()
        cls.minimum_karma_allowing_to_post = KARMA["ask"]
        cls.forums = cls.env["forum.forum"].create(
            [
                {
                    "name": f"Forum {idx + 2}",
                    "karma_ask": cls.minimum_karma_allowing_to_post,
                    "website_id": website.id,
                }
                for idx, website in enumerate(
                    (
                        cls.base_website,
                        cls.base_website,
                        cls.base_website,
                        cls.website_2,
                        cls.website_2,
                    )
                )
            ]
        )
        (
            cls.forum_1,
            cls.forum_2,
            cls.forum_3,
            cls.forum_1_website_2,
            cls.forum_2_website_2,
        ) = cls.forums
        cls.controller = WebsiteForum()

    def _get_my_other_forums(self, forum):
        return self.forums & self.controller._prepare_user_values(forum=forum).get(
            "my_other_forums"
        )

    def forum_post(self, user, forum):
        return (
            self.env["forum.post"]
            .with_user(user)
            .create(
                {
                    "content": "A post ...",
                    "forum_id": forum.id,
                    "name": "Post...",
                }
            )
        )

    def test_prepare_user_values_my_other_forum(self):
        employee_2_forum_2_post = self.forum_post(self.user_employee_2, self.forum_2)
        employee_2_website_2_forum_2_post = self.forum_post(
            self.user_employee_2, self.forum_2_website_2
        )
        for user in (
            self.user_admin,
            self.user_employee,
            self.user_portal,
            self.user_public,
        ):
            with (
                self.with_user(user.login),
                MockRequest(self.env, website=self.base_website),
            ):
                self.assertFalse(self._get_my_other_forums(self.forum_1))
                self.assertFalse(self._get_my_other_forums(None))
                self.assertFalse(self._get_my_other_forums(True))
                if user != self.user_public:
                    self.env.user.karma = self.minimum_karma_allowing_to_post
                    employee_2_forum_2_post.favorite_user_ids += self.env.user
                    self.assertEqual(
                        self._get_my_other_forums(self.forum_1), self.forum_2
                    )
                    self.assertFalse(self._get_my_other_forums(self.forum_2))
                    self.forum_post(self.env.user, self.forum_3)
                    self.forum_post(self.env.user, self.forum_1_website_2)
                    self.assertEqual(
                        self._get_my_other_forums(self.forum_1),
                        self.forum_2 + self.forum_3,
                    )
                    self.assertEqual(
                        self._get_my_other_forums(self.forum_2), self.forum_3
                    )
                    self.assertEqual(
                        self._get_my_other_forums(self.forum_3), self.forum_2
                    )
            with (
                self.with_user(user.login),
                MockRequest(self.env, website=self.website_2),
            ):
                self.assertFalse(self._get_my_other_forums(None))
                self.assertFalse(self._get_my_other_forums(True))
                if user != self.user_public:
                    self.assertFalse(self._get_my_other_forums(self.forum_1_website_2))
                    self.assertEqual(
                        self._get_my_other_forums(self.forum_2_website_2),
                        self.forum_1_website_2,
                    )
                    employee_2_website_2_forum_2_post.favorite_user_ids += self.env.user
                    self.assertEqual(
                        self._get_my_other_forums(self.forum_1_website_2),
                        self.forum_2_website_2,
                    )


@tagged("post_install", "-at_install")
class TestForumZeroKarmaForm(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.forum = cls.env["forum.forum"].create(
            {
                "name": "Open forum",
                "karma_ask": 0,
                "karma_tag_create": 0,
                "karma_edit_retag": 0,
                "karma_comment_all": 7,
            }
        )
        new_test_user(cls.env, login="zero_karma", groups="base.group_user", karma=0)

    def test_a_zero_karma_reaches_the_ask_form(self):
        forum = self.forum
        self.authenticate("zero_karma", "zero_karma")

        response = self.url_open(f"/forum/{self.env['ir.http']._slug(forum)}/ask")

        self.assertEqual(response.status_code, 200)
        page = html.fromstring(response.content)
        for input_id in ("karma", "karma_tag_create", "karma_edit_retag"):
            with self.subTest(input_id=input_id):
                [input_el] = page.xpath(f"//input[@id='{input_id}']")
                self.assertEqual(input_el.get("value"), "0")

    def test_the_comment_link_carries_the_karma_it_requires(self):
        question = self.env["forum.post"].create(
            {"forum_id": self.forum.id, "name": "Question", "content": "Body"}
        )
        self.authenticate("zero_karma", "zero_karma")
        slug = self.env["ir.http"]._slug

        response = self.url_open(f"/forum/{slug(self.forum)}/{slug(question)}")

        self.assertEqual(response.status_code, 200)
        links = html.fromstring(response.content).xpath(
            "//a[contains(@class, 'karma_required')][.//i[contains(@class, 'fa-comment')]]"
        )
        self.assertTrue(links)
        self.assertEqual({link.get("data-karma") for link in links}, {"7"})


@tagged("post_install", "-at_install")
class TestForumPostRoutes(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.asker = new_test_user(
            cls.env, login="forum_asker", groups="base.group_user", karma=100
        )
        cls.forum = cls.env["forum.forum"].create(
            {"name": "Routes Forum", "karma_ask": 0, "karma_answer": 0}
        )
        cls.question = (
            cls.env["forum.post"]
            .with_user(cls.asker)
            .create({"forum_id": cls.forum.id, "name": "Question", "content": "Q"})
        )
        cls.answer = cls.env["forum.post"].create(
            {
                "forum_id": cls.forum.id,
                "parent_id": cls.question.id,
                "name": "Answer",
                "content": "A",
            }
        )

    def _post_url(self, post, action):
        slug = self.env["ir.http"]._slug
        return f"/forum/{slug(self.forum)}/post/{slug(post)}/{action}"

    def _post(self, post, action, headers=None, **values):
        return self.url_open(
            self._post_url(post, action),
            data={"csrf_token": http.Request.csrf_token(self), **values},
            headers=headers,
            allow_redirects=False,
        )

    def test_an_empty_question_is_refused_as_a_bad_request(self):
        self.authenticate("admin", "admin")
        slug = self.env["ir.http"]._slug

        refused = self.url_open(
            f"/forum/{slug(self.forum)}/new",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "post_name": "A title",
                "content": "<p><br></p>",
            },
            allow_redirects=False,
        )

        self.assertEqual(refused.status_code, 400)
        self.assertIn("Question should not be empty.", refused.text)

    def test_a_question_cannot_be_marked_as_the_correct_answer(self):
        self.authenticate("admin", "admin")

        refused = self._post(self.question, "toggle_correct")

        self.assertEqual(refused.status_code, 404)
        self.assertFalse(self.question.is_correct)

    def test_marking_the_correct_answer_returns_to_the_page_given(self):
        self.authenticate("forum_asker", "forum_asker")

        response = self._post(self.answer, "toggle_correct", redirect="/forum/x?y=1")

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/forum/x?y=1"))
        self.assertTrue(self.answer.is_correct)

    def test_starring_a_question_returns_to_the_page_given_and_toggles(self):
        self.authenticate("forum_asker", "forum_asker")
        slug = self.env["ir.http"]._slug
        url = (
            f"/forum/{slug(self.forum)}/question/{slug(self.question)}/toggle_favorite"
        )
        question = self.question.with_user(self.asker)

        def star():
            response = self.url_open(
                url,
                data={
                    "csrf_token": http.Request.csrf_token(self),
                    "redirect": "/forum/x?y=1",
                },
                allow_redirects=False,
            )
            question.invalidate_recordset()
            return response, question.is_user_favorite

        (starred, favorite), (unstarred, still_favorite) = star(), star()

        self.assertEqual(starred.status_code, 303)
        self.assertTrue(starred.headers["Location"].endswith("/forum/x?y=1"))
        self.assertTrue(favorite)
        self.assertEqual(unstarred.status_code, 303)
        self.assertFalse(still_favorite)

    def test_a_vote_returns_to_the_question_and_counts(self):
        self.authenticate("forum_asker", "forum_asker")
        slug = self.env["ir.http"]._slug

        response = self._post(self.answer, "upvote")

        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            response.headers["Location"].endswith(
                f"/forum/{slug(self.forum)}/{slug(self.question)}"
            )
        )
        self.assertEqual(self.answer.vote_count, 1)

    def test_a_vote_on_ones_own_post_asked_in_place_is_refused_as_json(self):
        self.authenticate("forum_asker", "forum_asker")

        refused = self._post(self.question, "upvote", {"X-Odoo-Fragments": "1"})

        self.assertEqual(refused.status_code, 422)
        self.assertEqual(
            refused.json()["error"]["message"],
            "Sorry, you cannot vote for your own posts",
        )
        self.assertEqual(self.question.vote_count, 0)

    def _comment(self, author):
        return self.question.with_user(author).message_post(
            body="A comment", message_type="comment", subtype_xmlid="mail.mt_comment"
        )

    def _delete_comment_url(self, comment):
        slug = self.env["ir.http"]._slug
        return (
            f"/forum/{slug(self.forum)}/post/{slug(self.question)}"
            f"/comment/{slug(comment)}/delete"
        )

    def test_deleting_a_comment_returns_to_its_question(self):
        comment = self._comment(self.env.ref("base.user_admin"))
        self.authenticate("admin", "admin")
        slug = self.env["ir.http"]._slug

        response = self.url_open(
            self._delete_comment_url(comment),
            data={"csrf_token": http.Request.csrf_token(self)},
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            response.headers["Location"].endswith(
                f"/forum/{slug(self.forum)}/{slug(self.question)}"
            ),
            response.headers["Location"],
        )
        self.assertFalse(comment.exists())

    def test_a_refused_comment_delete_asked_in_place_answers_json(self):
        comment = self._comment(self.env.ref("base.user_admin"))
        self.forum.karma_comment_unlink_all = 1000
        self.authenticate("forum_asker", "forum_asker")

        response = self.url_open(
            self._delete_comment_url(comment),
            data={"csrf_token": http.Request.csrf_token(self)},
            headers={"X-Odoo-Fragments": "1"},
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.headers["Content-Type"].startswith("application/json"))
        self.assertIn("karma", response.json()["error"]["message"])
        self.assertTrue(comment.exists())

    def test_deleting_an_answer_returns_to_its_question(self):
        self.authenticate("admin", "admin")
        slug = self.env["ir.http"]._slug

        response = self.url_open(
            self._post_url(self.answer, "delete"),
            data={"csrf_token": http.Request.csrf_token(self)},
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            response.headers["Location"].endswith(
                f"/forum/{slug(self.forum)}/{slug(self.question)}"
            ),
            response.headers["Location"],
        )
