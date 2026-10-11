from odoo.tests.common import tagged

from odoo.addons.social.tests import common
from odoo.addons.social.tests.tools import mock_void_external_calls


@tagged("post_install", "-at_install")
class TestSocialPostGuard(common.SocialCase):
    @classmethod
    def _get_social_media(cls):
        return cls.env["social.media"].create({"name": "Social Media"})

    def _live_posts(self):
        return self.env["social.live.post"].search(
            [("post_id", "=", self.social_post.id)]
        )

    @mock_void_external_calls()
    def test_posting_an_already_posting_post_does_not_publish_it_again(self):
        self.social_post._action_post()
        first = self._live_posts()
        self.assertTrue(first, "the first call publishes")

        self.social_post._action_post()

        self.assertEqual(
            len(self._live_posts()),
            len(first),
            "a second call must not create a second set of live posts",
        )

    @mock_void_external_calls()
    def test_the_state_is_what_decides(self):
        self.social_post._action_post()
        self.assertEqual(self.social_post.state, "posting")

        self.social_post._action_post()

        self.assertEqual(self.social_post.state, "posting")

    @mock_void_external_calls()
    def test_a_draft_post_is_still_published(self):
        self.assertEqual(self.social_post.state, "draft")

        self.social_post._action_post()

        self.assertTrue(self._live_posts(), "the guard must not block a real post")
        self.assertEqual(self.social_post.state, "posting")
