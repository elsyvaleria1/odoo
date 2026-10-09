from odoo.tests import tagged

from odoo.addons.gamification.tests.common import HttpCaseGamification


@tagged("post_install", "-at_install")
class TestUi(HttpCaseGamification):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["forum.post"].create(
            {
                "name": "Very Smart Question",
                "forum_id": cls.env.ref("website_forum.forum_help").id,
            }
        )
        cls.env.ref("base.user_admin").write(
            {
                "email": "mitchell.admin@example.com",
            }
        )

    def test_01_admin_forum_tour(self):
        self.start_tour("/", "question", login="admin")

    def test_02_demo_question(self):
        forum = self.env.ref("website_forum.forum_help")
        demo = self.user_demo
        demo.karma = forum.karma_post + 1
        self.start_tour("/", "forum_question", login="demo")
        tags = self.env["forum.tag"].search(
            [("name", "in", ["Tag", "tag", "test tag"])]
        )
        self.assertEqual(len(tags), 3)

    def test_03_listing_filters_in_place(self):
        forum = self.env.ref("website_forum.forum_help")
        Post = self.env["forum.post"]
        answered = Post.create({"name": "PN Answered", "forum_id": forum.id})
        Post.create({"forum_id": forum.id, "parent_id": answered.id, "content": "Yes"})
        Post.create({"name": "PN Open", "forum_id": forum.id})
        self.start_tour(f"/forum/{forum.id}", "forum_partial_navigation")

    def test_04_comment_delete_in_place(self):
        question = self.env["forum.post"].create(
            {
                "name": "PN Question",
                "forum_id": self.env.ref("website_forum.forum_help").id,
            }
        )
        question.with_user(self.env.ref("base.user_admin")).message_post(
            body="PN doomed comment",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.start_tour(
            question.website_url, "forum_comment_delete_in_place", login="admin"
        )
        self.assertFalse(
            question.website_message_ids.filtered(
                lambda message: "PN doomed comment" in message.body
            )
        )

    def test_05_vote_in_place(self):
        forum = self.env.ref("website_forum.forum_help")
        question = self.env["forum.post"].create(
            {"name": "PN Votable", "forum_id": forum.id}
        )
        self.user_demo.karma = forum.karma_upvote + 1
        self.start_tour(question.website_url, "forum_vote_in_place", login="demo")
        self.assertEqual(question.vote_count, 1)

    def test_06_favorite_in_place(self):
        question = self.env["forum.post"].create(
            {
                "name": "PN Favorite",
                "forum_id": self.env.ref("website_forum.forum_help").id,
            }
        )
        self.start_tour(question.website_url, "forum_favorite_in_place", login="demo")
        self.assertTrue(question.with_user(self.user_demo).is_user_favorite)
