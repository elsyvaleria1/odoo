from odoo.tests import common

from odoo.addons.social.tests.tools import mock_void_external_calls


class SocialTestFullCase(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        media_refs = [
            "social_instagram.social_media_instagram",
            "social_facebook.social_media_facebook",
            "social_twitter.social_media_twitter",
            "social_linkedin.social_media_linkedin",
            "social_push_notifications.social_media_push_notifications",
            "social_youtube.social_media_youtube",
        ]

        with mock_void_external_calls():
            cls.accounts = cls.env["social.account"].create(
                [
                    {"media_id": cls.env.ref(media_ref).id, "name": "Account"}
                    for media_ref in media_refs
                ]
            )
