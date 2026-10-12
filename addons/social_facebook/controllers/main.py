import base64
import logging
import urllib.parse

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import fragment_to_query_string, request
from odoo.libs.json import loads as json_loads
from odoo.libs.web import urljoin as url_join

from odoo.addons.social.controllers.main import (
    SocialController,
    SocialValidationException,
)

_logger = logging.getLogger(__name__)


class SocialFacebookController(SocialController):
    @http.route(["/social_facebook/callback"], type="http", auth="user")
    @fragment_to_query_string
    def social_facebook_account_callback(  # noqa: E8539 -- inbound: a token an outside service hands over, not one of ours
        self, access_token=None, is_extended_token=False, **kw
    ):
        if not request.env.user.has_group("social.group_social_manager"):
            return request.render(
                "social.social_http_error_view",
                {
                    "error_message": request.env._(
                        "Unauthorized. Please contact your administrator. "
                    )
                },
            )

        if kw.get("error") != "access_denied":
            if not access_token:
                return request.render(
                    "social.social_http_error_view",
                    {
                        "error_message": request.env._(
                            "Facebook did not provide a valid access token."
                        )
                    },
                )

            if access_token:
                media = request.env.ref("social_facebook.social_media_facebook")
                if self._consume_oauth_state(media, kw.get("state")) is None:
                    return self._render_oauth_state_refused()

                try:
                    self._facebook_create_accounts(
                        access_token, media, is_extended_token
                    )
                except SocialValidationException as e:
                    return request.render(
                        "social.social_http_error_view",
                        {
                            "error_message": e.get_message(),
                            "documentation_data": e.get_documentation_data(),
                        },
                    )

        return request.redirect("/odoo/action-social.action_social_stream_post")

    @http.route("/social_facebook/comment", type="http", auth="user", methods=["POST"])
    def social_facebook_add_comment(
        self,
        stream_post_id=None,
        message=None,
        comment_id=None,
        existing_attachment_id=None,
        is_edit=False,
        **kwargs,
    ):
        stream_post = self._get_social_stream_post(stream_post_id, "facebook")
        attachment = None
        files = request.httprequest.files.getlist("attachment")
        if files and files[0]:
            attachment = files[0]

        if comment_id and is_edit:
            result = stream_post._facebook_comment_post(
                url_join(
                    request.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED, comment_id
                ),
                message,
                existing_attachment_id=existing_attachment_id,
                attachment=attachment,
            )
        elif comment_id:
            result = stream_post._facebook_comment_post(
                url_join(
                    request.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
                    "%s/comments" % (comment_id),
                ),
                message,
                existing_attachment_id=existing_attachment_id,
                attachment=attachment,
            )
        else:
            result = stream_post._facebook_comment_post(
                url_join(
                    request.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
                    "%s/comments" % (stream_post.facebook_post_id),
                ),
                message,
                existing_attachment_id=existing_attachment_id,
                attachment=attachment,
            )

        result["formatted_created_time"] = request.env[
            "social.stream.post"
        ]._format_facebook_published_date(result)
        return request.prepare_json_response(result)

    @http.route("/social_facebook/delete_comment", type="jsonrpc", auth="user")
    def social_facebook_delete_comment(self, stream_post_id, comment_id):
        stream_post = self._get_social_stream_post(stream_post_id, "facebook")
        stream_post._facebook_remove_comment(comment_id)

    @http.route("/social_facebook/get_comments", type="jsonrpc", auth="user")
    def social_facebook_get_comments(
        self, stream_post_id, next_records_token=False, comments_count=20
    ):
        stream_post = self._get_social_stream_post(stream_post_id, "facebook")
        return stream_post._facebook_get_comments(
            next_records_token, count=comments_count
        )

    @http.route("/social_facebook/like_comment", type="jsonrpc", auth="user")
    def social_facebook_like_comment(self, stream_post_id, comment_id, like):
        stream_post = self._get_social_stream_post(stream_post_id, "facebook")
        stream_post._facebook_like(comment_id, like)

    @http.route("/social_facebook/like_post", type="jsonrpc", auth="user")
    def social_facebook_like_post(self, stream_post_id, like):
        stream_post = self._get_social_stream_post(stream_post_id, "facebook")
        stream_post._facebook_like(stream_post.facebook_post_id, like)

    @http.route(
        ["/social_facebook/deletion_callback"],
        type="http",
        auth="receiver",
        receiver="social.media:_receiver_for_facebook_deletion",
        receiver_event="facebook_deletion",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def social_facebook_deletion_callback(self, **post):
        facebook_page_identifiers = request.admission.extra["facebook_page_identifiers"]
        if not facebook_page_identifiers:
            raise Forbidden

        accounts = (
            request.env["social.account"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [("facebook_account_id", "in", json_loads(facebook_page_identifiers))]
            )
        )
        _logger.info(
            "The following Social Facebook Accounts were requested to be deleted by the end user: %r",
            ", ".join(accounts.mapped("name")),
        )
        request.env["social.post"].sudo().search(
            [("account_ids", "in", accounts.ids)]
        ).unlink()
        request.env["social.post.template"].sudo().search(
            [("account_ids", "in", accounts.ids)]
        ).unlink()
        accounts.unlink()
        return "OK"

    @http.route(
        ["/social_facebook/redirect_to_profile/<int:account_id>/<facebook_user_id>"],
        type="http",
        auth="user",
    )
    def social_facebook_redirect_to_profile(
        self, account_id, facebook_user_id, name=""
    ):
        account = request.env["social.account"].browse(account_id)

        json_response = (
            request.env["ir.egress"]
            .request(
                "GET",
                url_join(
                    request.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
                    facebook_user_id,
                ),
                purpose="social_facebook",
                params={
                    "fields": "name,link",
                    "access_token": account.facebook_access_token,
                },
                timeout=5,
            )
            .json()
        )

        profile_url = json_response.get("link")
        if profile_url:
            redirect_url = profile_url
        else:
            redirect_url = "https://www.facebook.com/search/?q=%s" % urllib.parse.quote(
                name
            )

        return request.redirect(redirect_url, local=False)

    def _facebook_create_accounts(self, access_token, media, is_extended_token):

        extended_access_token = (
            access_token
            if is_extended_token
            else self._facebook_get_extended_access_token(access_token, media)
        )
        accounts_url = url_join(
            request.env["social.media"]._FACEBOOK_ENDPOINT, "/me/accounts/"
        )
        json_response = (
            request.env["ir.egress"]
            .request(
                "GET",
                accounts_url,
                purpose="social_facebook",
                params={
                    "fields": "id,access_token,name,username",
                    "access_token": extended_access_token,
                },
                timeout=5,
            )
            .json()
        )

        if "data" not in json_response:
            raise SocialValidationException(
                request.env._(
                    "Facebook did not provide a valid access token or it may have expired."
                )
            )
        if not json_response["data"]:
            message = request.env._(
                "You need to be the manager of a Facebook Page to post with Odoo Social.\n Please create one and make sure it is linked to your account."
            )
            documentation_link = "https://facebook.com/business/pages/manage"
            documentation_link_label = request.env._("Read More about Facebook Pages")
            documentation_link_icon_class = "fa-brands fa-facebook-f"
            raise SocialValidationException(
                message,
                documentation_link,
                documentation_link_label,
                documentation_link_icon_class,
            )

        accounts_to_create = []
        existing_accounts = self._facebook_get_existing_accounts(media, json_response)
        for account in json_response.get("data"):
            account_id = account["id"]
            access_token = account.get("access_token")
            social_account_handle = account.get("username")
            if existing_accounts.get(account_id):
                existing_accounts.get(account_id).write(
                    {
                        "active": True,
                        "facebook_access_token": access_token,
                        "social_account_handle": social_account_handle,
                        "is_media_disconnected": False,
                    }
                )
            else:
                accounts_to_create.append(
                    {
                        "name": account.get("name"),
                        "media_id": media.id,
                        "has_trends": True,
                        "facebook_account_id": account_id,
                        "facebook_access_token": access_token,
                        "social_account_handle": social_account_handle,
                        "image": self._facebook_get_profile_image(account_id),
                    }
                )

        if accounts_to_create:
            request.env["social.account"].create(accounts_to_create)

    def _facebook_get_extended_access_token(self, access_token, media):

        facebook_app_id = request.env.registry.settings.get(
            request.env, "social.facebook_app_id", False
        )
        facebook_client_secret = request.env[
            "credential.credential"
        ]._get_system_secret("social.facebook_client_secret")
        extended_token_url = url_join(
            request.env["social.media"]._FACEBOOK_ENDPOINT, "/oauth/access_token"
        )
        extended_token_request = request.env["ir.egress"].request(
            "POST",
            extended_token_url,
            purpose="social_facebook",
            params={
                "client_id": facebook_app_id,
                "client_secret": facebook_client_secret,
                "grant_type": "fb_exchange_token",
                "fb_exchange_token": access_token,
            },
            timeout=5,
        )
        return extended_token_request.json().get("access_token")

    def _facebook_get_profile_image(self, account_id):
        profile_image_url = url_join(
            request.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
            "%s/picture?height=300" % account_id,
        )
        return base64.b64encode(
            request.env["ir.egress"]
            .request("GET", profile_image_url, purpose="social_facebook", timeout=10)
            .content
        )

    def _facebook_get_existing_accounts(self, media_id, json_response):

        facebook_accounts_ids = [
            account["id"] for account in json_response.get("data", [])
        ]
        if facebook_accounts_ids:
            existing_accounts = (
                request.env["social.account"]
                .sudo()
                .with_context(active_test=False)
                .search(
                    [
                        ("media_id", "=", int(media_id)),
                        ("facebook_account_id", "in", facebook_accounts_ids),
                    ]
                )
            )

            error_message = existing_accounts._get_multi_company_error_message()
            if error_message:
                raise SocialValidationException(error_message)

            return {
                existing_account.facebook_account_id: existing_account
                for existing_account in existing_accounts
            }

        return {}
