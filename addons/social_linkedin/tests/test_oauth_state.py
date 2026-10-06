from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.social.tests.common_oauth import SocialOAuthStateMixin
from odoo.addons.social_linkedin.controllers.main import SocialLinkedinController


class LinkedinOAuthStateMixin(SocialOAuthStateMixin):
    MEDIA_XMLID = "social_linkedin.social_media_linkedin"
    CALLBACK = "/social_linkedin/callback"

    def _callback_params(self):
        return {"code": "a code"}

    @contextmanager
    def _patch_accounts_creation(self):
        with (
            patch.object(
                SocialLinkedinController,
                "_linkedin_get_access_token",
                return_value="a token",
            ),
            patch.object(
                type(self.env["social.account"]), "_create_linkedin_accounts"
            ) as create,
        ):
            yield create


@tagged("post_install", "-at_install")
class TestLinkedinOwnAppOAuthState(LinkedinOAuthStateMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("social.linkedin_use_own_account", True)
        ICP.set_param("social.linkedin_app_id", "an app")


@tagged("post_install", "-at_install")
class TestLinkedinIapOAuthState(LinkedinOAuthStateMixin, HttpCase):
    OWN_APP = False

    def _state_of(self, action, egress):
        return egress.call_args.kwargs["params"]["state"]
