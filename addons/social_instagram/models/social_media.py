from urllib.parse import urlencode as url_encode

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join


class SocialMedia(models.Model):
    _inherit = "social.media"

    _INSTAGRAM_ENDPOINT = "https://graph.facebook.com/"

    media_type = fields.Selection(selection_add=[("instagram", "Instagram")])

    def _action_add_account(self):
        self.check_singleton()

        if self.media_type != "instagram":
            return super()._action_add_account()

        instagram_app_id = self.env.registry.settings.get(
            self.env, "social.instagram_app_id", False
        )
        instagram_client_secret = self.env["credential.credential"]._get_system_secret(
            "social.instagram_client_secret"
        )
        if instagram_app_id and instagram_client_secret:
            return self._add_instagram_accounts_from_configuration(instagram_app_id)
        else:
            return self._add_instagram_accounts_from_iap()

    def _add_instagram_accounts_from_configuration(self, instagram_app_id) -> dict:
        base_url = self.get_base_url()
        base_instagram_url = "https://www.facebook.com/v17.0/dialog/oauth?%s"

        params = {
            "client_id": instagram_app_id,
            "redirect_uri": url_join(base_url, "social_instagram/callback"),
            "response_type": "token",
            "state": self._issue_oauth_state(),
            "scope": "instagram_basic,instagram_content_publish,instagram_manage_comments,instagram_manage_insights,pages_show_list,pages_manage_ads,pages_manage_metadata,pages_read_engagement,pages_read_user_content,pages_manage_engagement,pages_manage_posts,read_insights,business_management",
        }

        return {
            "type": "ir.actions.act_url",
            "url": base_instagram_url % url_encode(params),
            "target": "self",
        }

    def _add_instagram_accounts_from_iap(self) -> dict:
        base_url = self.get_base_url()
        social_iap_endpoint = self.env.registry.settings.get(
            self.env,
            "social.social_iap_endpoint",
            self.env["social.media"]._DEFAULT_SOCIAL_IAP_ENDPOINT,
        )

        iap_add_accounts_url = (
            self.env["ir.egress"]
            .request(
                "GET",
                url_join(social_iap_endpoint, "api/social/instagram/1/add_accounts"),
                purpose="social_instagram",
                params={
                    "returning_url": url_join(base_url, "social_instagram/callback"),
                    "csrf_token": self._issue_oauth_state(),
                    "db_uuid": self.env.registry.settings.get(
                        self.env, "database.uuid", False
                    ),
                },
                timeout=5,
            )
            .text
        )

        if iap_add_accounts_url == "unauthorized":
            raise UserError(
                self.env._(
                    "Oops! You currently don't have an active subscription. No worries, though! "
                    "You can easily get one here: %s.\n"
                    "Grab a subscription and unlock a world of amazing features!",
                    "https://www.odoo.com/buy",
                )
            )

        return {
            "type": "ir.actions.act_url",
            "url": iap_add_accounts_url,
            "target": "self",
        }
