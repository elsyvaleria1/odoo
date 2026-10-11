from odoo import http
from odoo.exceptions import MissingError
from odoo.http import request
from odoo.tools import consume_session_state, plaintext2html

from odoo.addons.social.models.social_media import (
    OAUTH_STATE_SCOPE,
    UNCARRIED_STATE_SESSION_KEY,
)


class SocialValidationException(Exception):
    def __init__(
        self,
        message,
        documentation_link=False,
        documentation_link_label=False,
        documentation_link_icon_class=False,
    ):
        self.message = message
        self.documentation_link = documentation_link
        self.documentation_link_label = documentation_link_label
        self.documentation_link_icon_class = documentation_link_icon_class
        super().__init__(message)

    def get_message(self):
        return plaintext2html(self.message)

    def get_documentation_data(self):
        return {
            "documentation_link": self.documentation_link,
            "documentation_link_label": self.documentation_link_label,
            "documentation_link_icon_class": self.documentation_link_icon_class,
        }


class SocialController(http.Controller):
    def _consume_oauth_state(self, media, state=None):
        uncarried = request.session.pop(UNCARRIED_STATE_SESSION_KEY, None)
        claims = consume_session_state(
            request.env, OAUTH_STATE_SCOPE, request.session, state or uncarried
        )
        if claims is None or claims.pop("media_id", None) != media.id:
            return None
        return claims

    def _render_oauth_state_refused(self):
        return request.render(
            "social.social_http_error_view",
            {
                "error_message": request.env._(
                    "There was a authentication issue during your request."
                )
            },
            status=403,
        )

    def _get_social_stream_post(self, stream_post_id, media_type):
        stream_post = request.env["social.stream.post"].search(
            [
                ("id", "=", stream_post_id),
                ("stream_id.account_id.media_id.media_type", "=", media_type),
            ]
        )
        if not stream_post:
            raise MissingError(
                request.env._(
                    "Uh-oh! It looks like this message has been deleted from X."
                )
            )

        return stream_post
