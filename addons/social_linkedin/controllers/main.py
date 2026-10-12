from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.social.controllers.main import (
    SocialController,
    SocialValidationException,
)


class SocialLinkedinController(SocialController):
    @http.route("/social_linkedin/callback", type="http", auth="user")
    def social_linkedin_callback(self, access_token=None, code=None, state=None, **kw):  # noqa: E8539 -- inbound: a token an outside service hands over, not one of ours
        if not request.env.user.has_group("social.group_social_manager"):
            return request.render(
                "social.social_http_error_view",
                {
                    "error_message": request.env._(
                        "Unauthorized. Please contact your administrator."
                    )
                },
            )

        if kw.get("error") not in ("user_cancelled_authorize", "user_cancelled_login"):
            if not access_token and not code:
                return request.render(
                    "social.social_http_error_view",
                    {
                        "error_message": request.env._(
                            "LinkedIn did not provide a valid access token."
                        )
                    },
                )

            media = request.env.ref("social_linkedin.social_media_linkedin")

            if self._consume_oauth_state(media, state) is None:
                return self._render_oauth_state_refused()

            try:
                if not access_token:
                    access_token = self._linkedin_get_access_token(code, media)

                request.env["social.account"]._create_linkedin_accounts(
                    access_token, media
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

    @http.route("/social_linkedin/comment", type="http", auth="user", methods=["POST"])
    def social_linkedin_add_comment(
        self, stream_post_id, message=None, comment_id=None, is_edit=False, **kwargs
    ):
        stream_post = self._get_social_stream_post(stream_post_id, "linkedin")
        if is_edit:
            return request.prepare_json_response(
                stream_post._linkedin_comment_edit(message, comment_id)
            )

        attachment = None
        files = request.httprequest.files.getlist("attachment")
        if files and files[0]:
            attachment = files[0].read()
        try:
            result = stream_post._linkedin_comment_add(message, comment_id, attachment)
        except UserError as e:
            result = {"error": str(e)}
        return request.prepare_json_response(result)

    @http.route("/social_linkedin/delete_comment", type="jsonrpc", auth="user")
    def social_linkedin_delete_comment(self, stream_post_id, comment_id, **kwargs):
        stream_post = self._get_social_stream_post(stream_post_id, "linkedin")
        return stream_post._linkedin_remove_comment(comment_id)

    @http.route("/social_linkedin/get_comments", type="jsonrpc", auth="user")
    def social_linkedin_get_comments(
        self, stream_post_id, comment_urn=None, offset=0, comments_count=20
    ):
        stream_post = self._get_social_stream_post(stream_post_id, "linkedin")
        return stream_post._linkedin_get_comments(
            comment_urn=comment_urn, offset=offset, count=comments_count
        )

    @http.route("/social_linkedin/like_comment", type="jsonrpc", auth="user")
    def social_linkedin_like_comment(self, stream_post_id, comment_id, like):
        stream_post = self._get_social_stream_post(stream_post_id, "linkedin")
        return stream_post._linkedin_like_comment(comment_id, like)

    @http.route("/social_linkedin/edit_post", type="jsonrpc", auth="user")
    def social_linkedin_edit_post(self, stream_post_id, new_message):
        stream_post = self._get_social_stream_post(stream_post_id, "linkedin")
        return stream_post._linkedin_edit_post(new_message)

    @http.route("/social_linkedin/delete_post", type="jsonrpc", auth="user")
    def social_linkedin_delete_post(self, stream_post_id):
        stream_post = self._get_social_stream_post(stream_post_id, "linkedin")
        return stream_post._linkedin_remove_post()

    def _linkedin_get_access_token(self, linkedin_authorization_code, media):
        linkedin_url = "https://www.linkedin.com/oauth/v2/accessToken"
        linkedin_app_id = request.env.registry.settings.get(
            request.env, "social.linkedin_app_id", False
        )
        linkedin_client_secret = request.env[
            "credential.credential"
        ]._get_system_secret("social.linkedin_client_secret")

        params = {
            "grant_type": "authorization_code",
            "code": linkedin_authorization_code,
            "redirect_uri": media._get_linkedin_redirect_uri(),
            "client_id": linkedin_app_id,
            "client_secret": linkedin_client_secret,
        }

        response = (
            request.env["ir.egress"]
            .request(
                "POST", linkedin_url, purpose="social_linkedin", data=params, timeout=5
            )
            .json()
        )

        error_description = response.get("error_description")
        if error_description:
            raise SocialValidationException(error_description)

        return response.get("access_token")
