from unittest.mock import patch

from odoo.addons.social.tests.common import SocialCase
from odoo.addons.social_facebook.models.social_account import SocialAccount


class SocialFacebookCommon(SocialCase):
    @classmethod
    def setUpClass(cls):
        with (
            patch.object(SocialAccount, "_update_statistics", lambda x: None),
            patch.object(
                SocialAccount,
                "_create_default_stream_facebook",
                lambda *args, **kwargs: None,
            ),
        ):
            super().setUpClass()
