from urllib.parse import urlencode as url_encode

import dateutil.parser

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join


class SocialMedia(models.Model):
    _inherit = "social.media"

    _YOUTUBE_ENDPOINT = "https://www.googleapis.com"

    media_type = fields.Selection(selection_add=[("youtube", "YouTube")])

    def _action_add_account(self):
        self.check_singleton()

        if self.media_type != "youtube":
            return super()._action_add_account()

        youtube_oauth_client_id = self.env.registry.settings.get(
            self.env, "social.youtube_oauth_client_id", False
        )
        youtube_oauth_client_secret = self.env[
            "credential.credential"
        ]._get_system_secret("social.youtube_oauth_client_secret")
        if youtube_oauth_client_id and youtube_oauth_client_secret:
            return self._add_youtube_accounts_from_configuration(
                youtube_oauth_client_id
            )
        else:
            return self._add_youtube_accounts_from_iap()

    def _add_youtube_accounts_from_configuration(self, youtube_oauth_client_id) -> dict:

        base_youtube_url = "https://accounts.google.com/o/oauth2/v2/auth?%s"
        params = {
            "client_id": youtube_oauth_client_id,
            "redirect_uri": url_join(self.get_base_url(), "social_youtube/callback"),
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube.force-ssl https://www.googleapis.com/auth/youtube.upload",
            "access_type": "offline",
            "prompt": "consent",
            "state": self._issue_oauth_state(),
        }

        return {
            "type": "ir.actions.act_url",
            "url": base_youtube_url % url_encode(params),
            "target": "self",
        }

    def _add_youtube_accounts_from_iap(self) -> dict:
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
                url_join(social_iap_endpoint, "api/social/youtube/1/add_accounts"),
                purpose="social_youtube",
                params={
                    "returning_url": url_join(
                        self.get_base_url(), "social_youtube/callback"
                    ),
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
        if iap_add_accounts_url == "youtube_missing_configuration":
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

    @api.model
    def _format_youtube_comment(self, youtube_comment) -> dict:
        comment_snippet = youtube_comment["snippet"]
        return {
            "id": youtube_comment.get("id"),
            "message": comment_snippet.get("textDisplay"),
            "from": {
                "id": comment_snippet.get("authorChannelId", {}).get("value"),
                "name": comment_snippet.get("authorDisplayName"),
                "author_image_url": comment_snippet.get("authorProfileImageUrl"),
                "author_channel_url": comment_snippet.get("authorChannelUrl"),
            },
            "created_time": comment_snippet.get("publishedAt"),
            "formatted_created_time": self.env[
                "social.stream.post"
            ]._format_published_date(
                fields.Datetime.from_string(
                    dateutil.parser.parse(comment_snippet.get("publishedAt")).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            ),
            "likes": {"summary": {"total_count": comment_snippet.get("likeCount")}},
        }
