from odoo import models


class SocialAccount(models.Model):
    _inherit = "social.account"

    def _update_statistics(self):
        return

    def _create_default_stream_facebook(self) -> None:
        return

    def _create_default_stream_twitter(self) -> None:
        return

    def _create_default_stream_youtube(self) -> None:
        return

    def _refresh_youtube_token(self) -> None:
        return

    def _create_default_stream_instagram(self) -> None:
        return

    def twitter_get_user_by_username(self, query):
        partner = self.env.ref("social_demo.res_partner_2", raise_if_not_found=False)
        return {
            "name": partner.name,
            "profile_image_url": f"/web/image/res.partner/{partner.id}/avatar_128",
            "username": partner.name.replace(" ", "").lower(),
            "description": "https://example.com",
        }
