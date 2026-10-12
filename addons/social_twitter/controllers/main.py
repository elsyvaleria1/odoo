import base64
import logging

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.libs.web import urljoin as url_join
from odoo.tools import consteq

from odoo.addons.social.controllers.main import (
    SocialController,
    SocialValidationException,
)

_logger = logging.getLogger(__name__)


class SocialTwitterController(SocialController):
    @http.route("/social_twitter/callback", type="http", auth="user")
    def social_twitter_account_callback(
        self, oauth_token=None, oauth_verifier=None, iap_twitter_consumer_key=None, **kw
    ):
        if not request.env.user.has_group("social.group_social_manager"):
            return request.render(
                "social.social_http_error_view",
                {
                    "error_message": request.env._(
                        "Unauthorized. Please contact your administrator."
                    )
                },
            )

        if not kw.get("denied"):
            if not oauth_token or not oauth_verifier:
                return request.render(
                    "social.social_http_error_view",
                    {
                        "error_message": request.env._(
                            "X did not provide a valid access token."
                        )
                    },
                )

            media = request.env["social.media"].search(
                [("media_type", "=", "twitter")], limit=1
            )
            claims = self._consume_oauth_state(media, kw.get("state"))
            if claims is None or (
                "oauth_token" in claims
                and not consteq(oauth_token, claims["oauth_token"])
            ):
                return self._render_oauth_state_refused()

            if iap_twitter_consumer_key and claims.get("iap"):
                request.env["ir.config_parameter"].sudo().set_param(
                    "social.twitter_consumer_key", iap_twitter_consumer_key
                )

            try:
                self._twitter_create_accounts(oauth_token, oauth_verifier, media)
            except SocialValidationException as e:
                return request.render(
                    "social.social_http_error_view",
                    {
                        "error_message": e.get_message(),
                        "documentation_data": e.get_documentation_data(),
                    },
                )
            except UserError as e:
                return request.render(
                    "social.social_http_error_view", {"error_message": str(e)}
                )

        return request.redirect("/odoo/action-social.action_social_stream_post")

    @http.route(
        "/social_twitter/<int:stream_id>/comment", type="http", methods=["POST"]
    )
    def social_twitter_comment(
        self,
        stream_id=None,
        stream_post_id=None,
        comment_id=None,
        message=None,
        answering_to=None,
        **kwargs,
    ):
        stream = request.env["social.stream"].browse(stream_id)
        if not stream.exists() or stream.media_id.media_type != "twitter":
            raise Forbidden

        stream_post = self._get_social_stream_post(stream_post_id, "twitter")
        answering_to = answering_to if comment_id else stream_post.twitter_screen_name

        message = request.env["social.live.post"]._remove_mentions(
            message, [answering_to]
        )

        files = request.httprequest.files.getlist("attachment")
        attachment = files and files[0]
        try:
            return request.prepare_json_response(
                stream_post._twitter_comment_add(
                    stream, comment_id, message, attachment
                )
            )
        except UserError as e:
            return request.prepare_json_response({"error": str(e)})

    @http.route("/social_twitter/delete_tweet", type="jsonrpc")
    def social_twitter_delete_tweet(self, stream_post_id, comment_id):
        stream_post = self._get_social_stream_post(stream_post_id, "twitter")
        return stream_post._twitter_remove_tweet(comment_id)

    @http.route("/social_twitter/get_comments", type="jsonrpc")
    def social_twitter_get_comments(self, stream_post_id, page=1):
        stream_post = self._get_social_stream_post(stream_post_id, "twitter")
        return stream_post._twitter_get_comments(page)

    @http.route("/social_twitter/<int:stream_id>/like_tweet", type="jsonrpc")
    def social_twitter_like_tweet(self, stream_id, tweet_id, like):
        stream = request.env["social.stream"].browse(stream_id)
        if not stream.exists() or stream.media_id.media_type != "twitter":
            raise Forbidden

        return request.env["social.stream.post"]._twitter_tweet_like(
            stream, tweet_id, like
        )

    @http.route("/social_twitter/<int:stream_id>/retweet", type="jsonrpc", auth="user")
    def social_twitter_do_retweet(self, stream_id, tweet_id):
        if not stream_id or not tweet_id:
            raise NotFound
        tweet = request.env["social.stream.post"].search(
            [("twitter_tweet_id", "=", tweet_id), ("stream_id", "=", stream_id)],
            limit=1,
        )
        if not tweet:
            raise UserError(request.env._("This Post has been deleted."))
        try:
            return tweet._twitter_do_retweet()
        except UserError as error:
            return json_dumps({"error": str(error)})

    @http.route(
        "/social_twitter/<int:stream_id>/unretweet", type="jsonrpc", auth="user"
    )
    def social_twitter_undo_retweet(self, stream_id, tweet_id):
        if not stream_id or not tweet_id:
            raise NotFound
        tweet = request.env["social.stream.post"].search(
            [("twitter_tweet_id", "=", tweet_id), ("stream_id", "=", stream_id)],
            limit=1,
        )
        if not tweet.exists():
            raise UserError(request.env._("This Post has been deleted."))
        try:
            return tweet._twitter_undo_retweet()
        except UserError as error:
            return json_dumps({"error": str(error)})

    @http.route(
        "/social_twitter/<int:stream_id>/quote",
        type="http",
        methods=["POST"],
        auth="user",
    )
    def social_twitter_tweet_quote(self, stream_id, tweet_id, message):
        if not stream_id or not tweet_id:
            raise NotFound
        tweet = request.env["social.stream.post"].search(
            [("twitter_tweet_id", "=", tweet_id), ("stream_id", "=", stream_id)],
            limit=1,
        )
        if not tweet:
            return request.prepare_json_response(
                {"error": request.env._("This Post has been deleted.")}
            )
        files = request.httprequest.files.getlist("attachment")
        attachment = files and files[0]
        try:
            return request.prepare_json_response(
                tweet._twitter_tweet_quote(message, attachment)
            )
        except UserError as error:
            return request.prepare_json_response({"error": str(error)})

    def _twitter_create_accounts(self, oauth_token, oauth_verifier, media):
        twitter_consumer_key = request.env.registry.settings.get(
            request.env, "social.twitter_consumer_key", False
        )

        twitter_access_token_url = url_join(
            request.env["social.media"]._TWITTER_ENDPOINT, "oauth/access_token"
        )
        response = request.env["ir.egress"].request(
            "POST",
            twitter_access_token_url,
            purpose="social_twitter",
            data={
                "oauth_consumer_key": twitter_consumer_key,
                "oauth_token": oauth_token,
                "oauth_verifier": oauth_verifier,
            },
            timeout=5,
        )

        if response.status_code != 200:
            message = request.env._(
                "X did not provide a valid access token or it may have expired."
            )
            documentation_link = "https://help.twitter.com/en/forms/account-access"
            documentation_link_label = request.env._("Read More about X Accounts")
            documentation_link_icon_class = "fa-brands fa-twitter"
            raise SocialValidationException(
                message,
                documentation_link,
                documentation_link_label,
                documentation_link_icon_class,
            )

        response_values = {
            response_value.split("=")[0]: response_value.split("=")[1]
            for response_value in response.text.split("&")
        }

        existing_account = (
            request.env["social.account"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("media_id", "=", media.id),
                    ("twitter_user_id", "=", response_values["user_id"]),
                ]
            )
        )

        error_message = existing_account._get_multi_company_error_message()
        if error_message:
            raise SocialValidationException(error_message)

        if existing_account:
            existing_account.write(
                {
                    "active": True,
                    "is_media_disconnected": False,
                    "social_account_handle": response_values["screen_name"],
                    "twitter_oauth_token": response_values["oauth_token"],
                    "twitter_oauth_token_secret": response_values["oauth_token_secret"],
                }
            )
        else:
            twitter_account_information = self._twitter_get_account_information(
                media,
                response_values["oauth_token"],
                response_values["oauth_token_secret"],
            )

            request.env["social.account"].create(
                {
                    "media_id": media.id,
                    "name": twitter_account_information["name"],
                    "twitter_user_id": response_values["user_id"],
                    "social_account_handle": response_values["screen_name"],
                    "twitter_oauth_token": response_values["oauth_token"],
                    "twitter_oauth_token_secret": response_values["oauth_token_secret"],
                    "image": base64.b64encode(
                        request.env["ir.egress"]
                        .request(
                            "GET",
                            twitter_account_information["profile_image_url"],
                            purpose="social_twitter",
                            timeout=10,
                        )
                        .content
                    ),
                }
            )

    def _twitter_get_account_information(self, media, oauth_token, oauth_token_secret):
        twitter_account_info_url = url_join(
            request.env["social.media"]._TWITTER_ENDPOINT, "/2/users/me"
        )

        params = {"user.fields": "profile_image_url"}
        headers = media._get_twitter_oauth_header(
            twitter_account_info_url,
            headers={
                "oauth_token": oauth_token,
                "oauth_token_secret": oauth_token_secret,
            },
            params=params,
            method="GET",
        )
        response = request.env["ir.egress"].request(
            "GET",
            twitter_account_info_url,
            purpose="social_twitter",
            headers=headers,
            params=params,
            timeout=5,
        )
        if not response.ok:
            raise SocialValidationException(
                request.env._("Authentication failed. Please enter valid credentials.")
            )
        return response.json()["data"]
