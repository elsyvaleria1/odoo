from urllib.parse import urlencode as url_encode

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join


class SocialMedia(models.Model):
    _inherit = "social.media"

    _LINKEDIN_ENDPOINT = "https://api.linkedin.com/rest/"
    _LINKEDIN_SCOPE = "r_basicprofile r_organization_followers w_member_social w_member_social_feed rw_organization_admin w_organization_social w_organization_social_feed r_organization_social r_organization_social_feed"

    media_type = fields.Selection(selection_add=[("linkedin", "LinkedIn")])

    def _action_add_account(self):
        self.check_singleton()

        if self.media_type != "linkedin":
            return super()._action_add_account()

        linkedin_use_own_account = self.env.registry.settings.get_bool(
            self.env, "social.linkedin_use_own_account"
        )
        linkedin_app_id = self.env.registry.settings.get(
            self.env, "social.linkedin_app_id", False
        )
        linkedin_client_secret = self.env["credential.credential"]._get_system_secret(
            "social.linkedin_client_secret"
        )

        if linkedin_app_id and linkedin_client_secret and linkedin_use_own_account:
            return self._add_linkedin_accounts_from_configuration(linkedin_app_id)
        else:
            return self._add_linkedin_accounts_from_iap()

    def _add_linkedin_accounts_from_configuration(self, linkedin_app_id) -> dict:
        params = {
            "response_type": "code",
            "client_id": linkedin_app_id,
            "redirect_uri": self._get_linkedin_redirect_uri(),
            "state": self._issue_oauth_state(),
            "scope": self._LINKEDIN_SCOPE,
        }

        return {
            "type": "ir.actions.act_url",
            "url": "https://www.linkedin.com/oauth/v2/authorization?%s"
            % url_encode(params),
            "target": "self",
        }

    def _add_linkedin_accounts_from_iap(self) -> dict:
        o_redirect_uri = url_join(self.get_base_url(), "social_linkedin/callback")

        social_iap_endpoint = self.env.registry.settings.get(
            self.env,
            "social.social_iap_endpoint",
            self.env["social.media"]._DEFAULT_SOCIAL_IAP_ENDPOINT,
        )

        iap_add_accounts_url = (
            self.env["ir.egress"]
            .request(
                "GET",
                url_join(social_iap_endpoint, "api/social/linkedin/1/add_accounts"),
                purpose="social_linkedin",
                params={
                    "state": self._issue_oauth_state(),
                    "scope": self._LINKEDIN_SCOPE,
                    "o_redirect_uri": o_redirect_uri,
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
        if iap_add_accounts_url in {
            "linkedin_missing_configuration",
            "missing_parameters",
        }:
            raise UserError(
                self.env._(
                    "The url that this service requested returned an error. Please contact the author of the app."
                )
            )

        return {
            "type": "ir.actions.act_url",
            "url": iap_add_accounts_url,
            "target": "self",
        }

    def _get_linkedin_redirect_uri(self):
        return url_join(self.get_base_url(), "social_linkedin/callback")
