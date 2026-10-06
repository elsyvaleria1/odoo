from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.social_facebook.models.social_account import SocialAccount


@tagged("post_install", "-at_install")
class TestFacebookDeletionCallback(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = cls.env.ref("social_facebook.social_media_facebook")
        with (
            patch.object(SocialAccount, "_update_statistics", lambda x: None),
            patch.object(
                SocialAccount,
                "_create_default_stream_facebook",
                lambda *args, **kwargs: None,
            ),
        ):
            cls.account = cls.env["social.account"].create(
                {
                    "media_id": cls.media.id,
                    "name": "A Facebook Page",
                    "facebook_account_id": "42",
                }
            )

    def _request_deletion(self, secret):
        return self.url_open(
            "/social_facebook/deletion_callback",
            data={"secret": secret, "facebook_page_identifiers": json_dumps(["42"])},
        )

    @mute_logger("odoo.http", "odoo.addons.integration")
    def test_a_wrong_shared_secret_deletes_nothing(self):
        response = self._request_deletion("not the shared secret")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(self.account.exists())

    def test_the_shared_secret_deletes_the_requested_pages(self):
        response = self._request_deletion(
            self.media._get_social_facebook_deletion_shared_secret()
        )
        self.assertEqual(response.text, "OK")
        self.assertFalse(self.account.exists())
