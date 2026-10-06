from unittest.mock import MagicMock, patch

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.libs.guarded_http import GuardedSession
from odoo.tests import common

from odoo.addons.social_youtube.models.social_account import SocialAccount
from odoo.addons.social_youtube.models.social_stream import SocialStream


class SocialYouTubeCase(common.TransactionCase):
    def test_youtube_data_cleaning(self):
        with (
            patch.object(
                SocialAccount,
                "_create_default_stream_youtube",
                lambda *args, **kwargs: None,
            ),
            patch.object(SocialStream, "_sync_stream_data", lambda x: None),
        ):
            SocialStreamPost = self.env["social.stream.post"]
            youtube_media = self.env.ref("social_youtube.social_media_youtube")
            youtube_social_account = self.env["social.account"].create(
                {"media_id": youtube_media.id, "name": "Social Account"}
            )
            youtube_stream_type = self.env.ref(
                "social_youtube.stream_type_youtube_channel_videos"
            )
            youtube_stream = self.env["social.stream"].create(
                {
                    "name": "My Videos",
                    "media_id": youtube_media.id,
                    "account_id": youtube_social_account.id,
                    "stream_type_id": youtube_stream_type.id,
                }
            )

            [new_post, old_post] = SocialStreamPost.create(
                [
                    {"stream_id": youtube_stream.id},
                    {
                        "stream_id": youtube_stream.id,
                        "write_date": fields.Datetime.now() - relativedelta(days=31),
                    },
                ]
            )
            new_post_id = new_post.id
            old_post_id = old_post.id
            SocialStreamPost._gc_youtube_data()

            # 'old_post' should be automatically deleted as of YouTube ToS
            # see 'social.stream.post#_gc_youtube_data()' for more information
            self.assertEqual(
                new_post,
                SocialStreamPost.search([("id", "in", [new_post_id, old_post_id])]),
            )


class SocialYouTubeTokenRefresh(common.TransactionCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(
            SocialAccount, "_create_default_stream_youtube", lambda *a, **k: None
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env["ir.config_parameter"].sudo().set_param(
            "social.youtube_oauth_client_id", "yt-client"
        )
        self.env["credential.credential"]._set_system_secret(
            "social.youtube_oauth_client_secret", "yt-secret"
        )
        self.account = self.env["social.account"].create(
            {
                "media_id": self.env.ref("social_youtube.social_media_youtube").id,
                "name": "Channel",
                "youtube_access_token": "expired-access",
                "youtube_refresh_token": "held-refresh",
                "youtube_token_expiration_date": fields.Datetime.now()
                - relativedelta(minutes=1),
            }
        )

    def _refresh(self, payload):
        response = MagicMock(ok=True, status_code=200)
        response.json.return_value = payload
        with patch.object(GuardedSession, "request", return_value=response) as sent:
            self.account._refresh_youtube_token()
        return sent

    def test_an_expired_token_is_refreshed_with_the_held_refresh_token(self):
        sent = self._refresh({"access_token": "fresh-access", "expires_in": 3600})

        data = sent.call_args.kwargs["data"]
        self.assertEqual(
            (data["refresh_token"], data["client_id"], data["client_secret"]),
            ("held-refresh", "yt-client", "yt-secret"),
        )
        self.assertEqual(self.account.youtube_access_token, "fresh-access")
        self.assertEqual(self.account.youtube_refresh_token, "held-refresh")
        self.assertGreater(
            self.account.youtube_token_expiration_date,
            fields.Datetime.now() + relativedelta(minutes=59),
        )

    def test_an_account_holding_no_refresh_token_is_disconnected(self):
        self.account.youtube_refresh_token = False

        sent = self._refresh({})

        sent.assert_not_called()
        self.assertTrue(self.account.is_media_disconnected)
