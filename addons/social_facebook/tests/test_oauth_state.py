from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.social.tests.common_oauth import SocialOAuthStateMixin
from odoo.addons.social_facebook.controllers.main import SocialFacebookController


class FacebookOAuthStateMixin(SocialOAuthStateMixin):
    MEDIA_XMLID = "social_facebook.social_media_facebook"
    CALLBACK = "/social_facebook/callback"

    def _callback_params(self):
        return {"access_token": "a token", "is_extended_token": "1"}

    def _patch_accounts_creation(self):
        return patch.object(SocialFacebookController, "_facebook_create_accounts")


@tagged("post_install", "-at_install")
class TestFacebookOwnAppOAuthState(FacebookOAuthStateMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "social.facebook_app_id", "an app"
        )


@tagged("post_install", "-at_install")
class TestFacebookIapOAuthState(FacebookOAuthStateMixin, HttpCase):
    OWN_APP = False
    CARRIED = False
