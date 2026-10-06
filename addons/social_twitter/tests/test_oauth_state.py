from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.social.tests.common_oauth import SocialOAuthStateMixin
from odoo.addons.social_twitter.controllers.main import SocialTwitterController


class TwitterOAuthStateMixin(SocialOAuthStateMixin):
    MEDIA_XMLID = "social_twitter.social_media_twitter"
    CALLBACK = "/social_twitter/callback"
    CARRIED = False

    def _patch_accounts_creation(self):
        return patch.object(SocialTwitterController, "_twitter_create_accounts")


@tagged("post_install", "-at_install")
class TestTwitterOwnAppOAuthState(TwitterOAuthStateMixin, HttpCase):
    EGRESS_RESPONSE = SimpleNamespace(
        text="oauth_token=request-token&oauth_token_secret=s"
        "&oauth_callback_confirmed=true",
        status_code=200,
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "social.twitter_consumer_key", "own key"
        )

    def _callback_params(self):
        return {
            "oauth_token": "request-token",
            "oauth_verifier": "v",
            "iap_twitter_consumer_key": "injected key",
        }

    def test_a_callback_for_another_request_token_is_refused(self):
        self._start()
        with patch.object(
            self,
            "_callback_params",
            lambda: {
                "oauth_token": "another-token",
                "oauth_verifier": "v",
            },
        ):
            self._assert_refused(None)

    def test_an_own_app_flow_takes_no_consumer_key_from_the_query(self):
        self._start()
        self._assert_accepted(None)
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("social.twitter_consumer_key"),
            "own key",
        )


@tagged("post_install", "-at_install")
class TestTwitterIapOAuthState(TwitterOAuthStateMixin, HttpCase):
    OWN_APP = False

    def _callback_params(self):
        return {
            "oauth_token": "a token",
            "oauth_verifier": "v",
            "iap_twitter_consumer_key": "iap key",
        }

    def test_the_consumer_key_is_taken_only_with_the_state(self):
        self._assert_refused(None)
        self.assertNotEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("social.twitter_consumer_key"),
            "iap key",
        )
        self._start()
        self._assert_accepted(None)
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("social.twitter_consumer_key"),
            "iap key",
        )
