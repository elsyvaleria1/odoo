import base64
import contextlib
import hashlib
import hmac
import time
import uuid
from html import unescape
from urllib.parse import quote as url_quote

import dateutil.parser
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.libs.web import urljoin as url_join

from odoo.addons.iap.tools import iap_tools


def _oauth_quote(value):
    return url_quote(str(value), safe="")


class SocialMedia(models.Model):
    _inherit = "social.media"

    _TWITTER_ENDPOINT = "https://api.twitter.com"

    media_type = fields.Selection(selection_add=[("twitter", "X")])

    def _action_add_account(self):

        self.check_singleton()

        if self.media_type != "twitter":
            return super()._action_add_account()

        twitter_consumer_key = self.env.registry.settings.get(
            self.env, "social.twitter_consumer_key", False
        )
        twitter_consumer_secret_key = self.env[
            "credential.credential"
        ]._get_system_secret("social.twitter_consumer_secret_key")
        if twitter_consumer_key and twitter_consumer_secret_key:
            return self._add_twitter_accounts_from_configuration()
        return self._add_twitter_accounts_from_iap()

    def _add_twitter_accounts_from_configuration(self) -> dict:
        twitter_oauth_url = url_join(self._TWITTER_ENDPOINT, "oauth/request_token")

        headers = self._get_twitter_oauth_header(
            twitter_oauth_url,
            headers={
                "oauth_callback": url_join(
                    self.get_base_url(), "social_twitter/callback"
                )
            },
        )
        response = self.env["ir.egress"].request(
            "POST",
            twitter_oauth_url,
            purpose="social_twitter",
            headers=headers,
            timeout=5,
        )
        if response.status_code != 200:
            raise UserError(self._extract_error_message(response))

        response_values = {
            response_value.split("=")[0]: response_value.split("=")[1]
            for response_value in response.text.split("&")
        }

        self._issue_oauth_state(
            carried=False, oauth_token=response_values["oauth_token"]
        )
        twitter_authorize_url = url_join(self._TWITTER_ENDPOINT, "oauth/authorize")

        return {
            "name": "Add Account",
            "type": "ir.actions.act_url",
            "url": f"{twitter_authorize_url}?oauth_token={response_values['oauth_token']}",
            "target": "self",
        }

    def _add_twitter_accounts_from_iap(self) -> dict:
        social_iap_endpoint = self.env.registry.settings.get(
            self.env,
            "social.social_iap_endpoint",
            self.env["social.media"]._DEFAULT_SOCIAL_IAP_ENDPOINT,
        )

        self._issue_oauth_state(carried=False, iap=True)
        iap_add_accounts_url = (
            self.env["ir.egress"]
            .request(
                "GET",
                url_join(social_iap_endpoint, "api/social/twitter/1/add_accounts"),
                purpose="social_twitter",
                params={
                    "returning_url": url_join(
                        self.get_base_url(), "social_twitter/callback"
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
        if iap_add_accounts_url == "wrong_configuration":
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

    def _extract_error_message(self, response):
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        with contextlib.suppress(etree.XMLSyntaxError):
            document_root = etree.fromstring(response.content, parser)
            error_node = document_root.find("error")
            if error_node is not None and error_node.get("code") == "415":
                return self.env._(
                    "You need to add the following callback URL to your X application settings: %s",
                    url_join(self.get_base_url(), "social_twitter/callback"),
                )
        return response.text

    def _get_twitter_oauth_header(self, url, headers=None, params=None, method="POST"):

        twitter_consumer_key = self.env.registry.settings.get(
            self.env, "social.twitter_consumer_key", False
        )
        header_params = {
            "oauth_nonce": uuid.uuid4(),
            "oauth_consumer_key": twitter_consumer_key,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_version": "1.0",
        }
        headers = dict(headers or {})
        oauth_token_secret = headers.pop("oauth_token_secret", "")
        header_params.update(headers)

        signature_params = {}
        signature_params.update(header_params)
        signature_params.update(params or {})
        header_params["oauth_signature"] = self._get_twitter_oauth_signature(
            method, url, signature_params, oauth_token_secret=oauth_token_secret
        )
        header_oauth = "OAuth " + ", ".join(
            [
                ('%s="%s"' % (key, _oauth_quote(header_params[key])))
                for key in sorted(header_params.keys())
            ]
        )
        return {"Authorization": header_oauth}

    def _get_twitter_oauth_signature(self, method, url, params, oauth_token_secret=""):

        self.check_singleton()

        twitter_consumer_secret_key = self.env[
            "credential.credential"
        ]._get_system_secret("social.twitter_consumer_secret_key")
        if twitter_consumer_secret_key:
            return self._get_twitter_oauth_signature_from_configuration(
                method, url, params, twitter_consumer_secret_key, oauth_token_secret
            )
        return self._get_twitter_oauth_signature_from_iap(
            method, url, params, oauth_token_secret
        )

    def _get_twitter_oauth_signature_from_configuration(
        self, method, url, params, twitter_consumer_secret_key, oauth_token_secret=""
    ):
        signing_key = f"{twitter_consumer_secret_key}&{oauth_token_secret}"
        base_string = "&".join(
            [
                method,
                _oauth_quote(url),
                _oauth_quote(
                    "&".join(
                        [
                            (
                                "%s=%s"
                                % (
                                    _oauth_quote(key),
                                    _oauth_quote(params[key]),
                                )
                            )
                            for key in sorted(params.keys())
                        ]
                    ),
                ),
            ]
        )
        signed_sha1 = hmac.new(
            signing_key.encode(), base_string.encode(), hashlib.sha1
        ).digest()
        return base64.b64encode(signed_sha1).decode()

    def _get_twitter_oauth_signature_from_iap(
        self, method, url, params, oauth_token_secret=""
    ):
        params["oauth_nonce"] = str(params["oauth_nonce"])
        json_params = {
            "method": method,
            "url": url,
            "params": params,
            "oauth_token_secret": oauth_token_secret,
            "db_uuid": self.env.registry.settings.get(self.env, "database.uuid", False),
        }
        social_iap_endpoint = self.env.registry.settings.get(
            self.env,
            "social.social_iap_endpoint",
            self.env["social.media"]._DEFAULT_SOCIAL_IAP_ENDPOINT,
        )
        try:
            return iap_tools.iap_jsonrpc(
                url_join(social_iap_endpoint, "api/social/twitter/1/get_signature"),
                params=json_params,
                env=self.env,
            )
        except AccessError:
            return None

    @api.model
    def _format_tweet(self, tweet):
        if "created_at" in tweet:
            created_date = fields.Datetime.from_string(
                dateutil.parser.parse(tweet.get("created_at")).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        else:
            created_date = fields.Datetime.now()

        in_reply_to_tweet_id = next(
            (
                referenced["id"]
                for referenced in tweet.get("referenced_tweets", [])
                if referenced["type"] == "replied_to"
            ),
            None,
        )
        formatted_tweet = {
            "id": tweet.get("id"),
            "message": unescape(tweet.get("text", "")),
            "from": {
                "id": tweet.get("author_id"),
                "name": tweet.get("author", {}).get("name"),
                "screen_name": tweet.get("author", {}).get("username"),
                "profile_image_url": tweet.get("author", {}).get("profile_image_url"),
            },
            "created_time": tweet.get("created_at"),
            "formatted_created_time": self.env[
                "social.stream.post"
            ]._format_published_date(fields.Datetime.from_string(created_date)),
            "user_likes": False,
            "likes": {
                "summary": {
                    "total_count": tweet.get("public_metrics", {}).get("like_count", 0),
                },
            },
            "comments": {"data": []},
            "in_reply_to_tweet_id": in_reply_to_tweet_id,
        }

        attached_medias = tweet.get("medias")
        if attached_medias:
            if attached_medias[0].get("type") == "photo":
                formatted_tweet["attachment"] = {
                    "type": "photo",
                    "media": {
                        "image": {
                            "src": attached_medias[0].get("url"),
                        }
                    },
                }

        return formatted_tweet
