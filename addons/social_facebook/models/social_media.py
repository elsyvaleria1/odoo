from urllib.parse import urlencode as url_encode

from odoo import api, fields, models, tools
from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.web import urljoin as url_join

from odoo.addons.integration.tools.admission import Resolution

DELETION_SECRET_SCOPE = tools.register_signed_scope(
    "social_facebook-deletion_shared_secret",
    purpose="the secret IAP presents to forward a Facebook data deletion request",
    lifetime="undated: it changes with database.secret",
)


class SocialMedia(models.Model):
    _inherit = "social.media"

    _FACEBOOK_ENDPOINT = "https://graph.facebook.com"
    _FACEBOOK_ENDPOINT_VERSIONED = "%s/v17.0/" % _FACEBOOK_ENDPOINT

    media_type = fields.Selection(selection_add=[("facebook", "Facebook")])

    def _action_add_account(self):

        self.check_singleton()

        if self.media_type != "facebook":
            return super()._action_add_account()

        facebook_app_id = self.env.registry.settings.get(
            self.env, "social.facebook_app_id", False
        )
        facebook_client_secret = self.env["credential.credential"]._get_system_secret(
            "social.facebook_client_secret"
        )
        if facebook_app_id and facebook_client_secret:
            return self._add_facebook_accounts_from_configuration(facebook_app_id)
        else:
            return self._add_facebook_accounts_from_iap()

    def _add_facebook_accounts_from_configuration(self, facebook_app_id) -> dict:
        base_facebook_url = "https://www.facebook.com/v17.0/dialog/oauth?%s"
        scopes = [
            "pages_manage_ads",
            "pages_manage_metadata",
            "pages_read_engagement",
            "pages_read_user_content",
            "pages_manage_engagement",
            "pages_manage_posts",
            "read_insights",
        ]
        if not self.env.registry.settings.get(
            self.env, "social.facebook_no_business_management", False
        ):
            scopes.append("business_management")
        params = {
            "client_id": facebook_app_id,
            "redirect_uri": url_join(self.get_base_url(), "social_facebook/callback"),
            "response_type": "token",
            "scope": ",".join(scopes),
            "state": self._issue_oauth_state(),
        }

        return {
            "type": "ir.actions.act_url",
            "url": base_facebook_url % url_encode(params),
            "target": "self",
        }

    def _add_facebook_accounts_from_iap(self) -> dict:
        social_iap_endpoint = self.env.registry.settings.get(
            self.env,
            "social.social_iap_endpoint",
            self.env["social.media"]._DEFAULT_SOCIAL_IAP_ENDPOINT,
        )

        self._issue_oauth_state(carried=False)
        iap_add_accounts_url = (
            self.env["ir.egress"]
            .request(
                "GET",
                url_join(social_iap_endpoint, "api/social/facebook/1/add_accounts"),
                purpose="social_facebook",
                params={
                    "db_uuid": self.env.registry.settings.get(
                        self.env, "database.uuid", False
                    ),
                    "returning_url": url_join(
                        self.get_base_url(), "social_facebook/callback"
                    ),
                    "client_host_url": self.get_base_url(),
                    "deletion_shared_secret": self._get_social_facebook_deletion_shared_secret(),
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

    @api.model
    def _receiver_for_facebook_deletion(self, **path_args):
        media = self.env.ref(
            "social_facebook.social_media_facebook", raise_if_not_found=False
        )
        if not media:
            return self.browse()
        params = request.get_http_params()
        secret = params.get("secret") or ""
        identifiers = params.get("facebook_page_identifiers") or ""

        def is_request_authorized(headers, body) -> bool:
            return bool(secret) and tools.consteq(
                secret, media._get_social_facebook_deletion_shared_secret()
            )

        return Resolution(
            media,
            {"facebook_page_identifiers": identifiers},
            gate=(media, "Facebook data deletion", "deletion_callback"),
            verify=is_request_authorized,
        )

    def _get_social_facebook_deletion_shared_secret(self):
        return tools.hmac(self.env(su=True), DELETION_SECRET_SCOPE, None)
