from unittest.mock import patch

from odoo import modules
from odoo.tests.common import tagged

from odoo.addons.social.tests import common


@tagged("post_install", "-at_install")
class TestSocialPostAfterCommit(common.SocialCase):
    @classmethod
    def _get_social_media(cls):
        return cls.env["social.media"].create({"name": "Social Media"})

    def _live_posts(self):
        return self.env["social.live.post"].search(
            [("post_id", "=", self.social_post.id)]
        )

    def test_the_media_apis_run_only_once_the_claim_is_committed(self):
        LivePost = type(self.env["social.live.post"])
        with (
            patch.object(modules.module, "current_test", False),
            patch.object(LivePost, "_post", autospec=True) as media_api,
        ):
            self.social_post._action_post()
        self.assertFalse(media_api.called)
        self.assertEqual(self.social_post.state, "posting")
        self.assertTrue(self._live_posts())

        with (
            patch.object(
                LivePost, "_post", autospec=True, side_effect=RuntimeError("down")
            ) as media_api,
            self.sync_env_with_side_cursors(),
        ):
            self.env.cr.postcommit.run()

        self.assertTrue(media_api.called)
        self.env.invalidate_all()
        self.assertNotIn(self.social_post.state, ("draft", "scheduled"))
        self.assertEqual(set(self._live_posts().mapped("state")), {"failed"})
