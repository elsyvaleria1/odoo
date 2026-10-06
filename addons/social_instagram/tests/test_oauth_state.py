from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.social.tests.common_oauth import SocialOAuthStateMixin
from odoo.addons.social_instagram.controllers.main import SocialInstagramController


class InstagramOAuthStateMixin(SocialOAuthStateMixin):
    MEDIA_XMLID = "social_instagram.social_media_instagram"
    CALLBACK = "/social_instagram/callback"

    def _callback_params(self):
        return {"access_token": "a token"}

    def _patch_accounts_creation(self):
        return patch.object(SocialInstagramController, "_instagram_create_accounts")


@tagged("post_install", "-at_install")
class TestInstagramOwnAppOAuthState(InstagramOAuthStateMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "social.instagram_app_id", "an app"
        )


@tagged("post_install", "-at_install")
class TestInstagramIapOAuthState(InstagramOAuthStateMixin, HttpCase):
    OWN_APP = False

    def _state_of(self, action, egress):
        return egress.call_args.kwargs["params"]["csrf_token"]
