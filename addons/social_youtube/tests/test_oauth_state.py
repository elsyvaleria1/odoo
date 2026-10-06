from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.social.tests.common_oauth import SocialOAuthStateMixin
from odoo.addons.social_youtube.controllers.main import SocialYoutubeController


class YoutubeOAuthStateMixin(SocialOAuthStateMixin):
    MEDIA_XMLID = "social_youtube.social_media_youtube"
    CALLBACK = "/social_youtube/callback"

    @contextmanager
    def _patch_accounts_creation(self):
        tokens = {"access_token": "a", "refresh_token": "r", "expires_in": 3600}
        with (
            patch.object(
                type(self.env["ir.egress"]),
                "request",
                return_value=SimpleNamespace(json=lambda: tokens),
            ),
            patch.object(SocialYoutubeController, "_youtube_create_accounts") as create,
        ):
            yield create


@tagged("post_install", "-at_install")
class TestYoutubeOwnAppOAuthState(YoutubeOAuthStateMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "social.youtube_oauth_client_id", "a client"
        )

    def _callback_params(self):
        return {"code": "a code"}


@tagged("post_install", "-at_install")
class TestYoutubeIapOAuthState(YoutubeOAuthStateMixin, HttpCase):
    OWN_APP = False
    CARRIED = False

    def _callback_params(self):
        return {
            "iap_access_token": "a",
            "iap_refresh_token": "r",
            "iap_expires_in": "3600",
        }
