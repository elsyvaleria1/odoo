import logging

import werkzeug

from odoo import http
from odoo.http import request
from odoo.tools.misc import get_lang

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused
from odoo.addons.rating.models.rating_data import (
    RATING_HAPPY_VALUE,
    RATING_NEUTRAL_VALUE,
    RATING_UNHAPPY_VALUE,
)

_logger = logging.getLogger(__name__)


class Rating(http.Controller):
    @http.route(
        "/rate/<string:token>/<int:rate>", type="http", auth="public", website=True
    )
    def action_view_rating(self, token, rate, **kwargs):
        if rate not in (RATING_HAPPY_VALUE, RATING_NEUTRAL_VALUE, RATING_UNHAPPY_VALUE):
            raise ValueError(
                f"Incorrect rating: should be {RATING_UNHAPPY_VALUE}, "
                f"{RATING_NEUTRAL_VALUE} or {RATING_HAPPY_VALUE} (received {rate})"
            )

        # This route used to allow sending a rating with a GET, the
        # feature proved incompatible with various email provider URL crawlers and
        # has been removed.
        rating, record_sudo = self._get_rating_and_record(token)

        if not self._has_rating_partner_access(rating):
            return self._render_invalid_partner_page(rating, record_sudo)
        if not rating._is_open_through_link():
            return self._render_rating_page(rating)

        lang = rating.partner_id.lang or get_lang(request.env).code
        return (
            request.env["ir.ui.view"]
            .with_context(lang=lang)
            ._render_template(
                "rating.rating_external_page_submit",
                {
                    "rating": rating,
                    "token": token,
                    "rate_names": {
                        RATING_HAPPY_VALUE: request.env._("Happy"),
                        RATING_NEUTRAL_VALUE: request.env._("Neutral"),
                        RATING_UNHAPPY_VALUE: request.env._("Unhappy"),
                    },
                    "rate": rate,
                },
            )
        )

    @http.route(
        ["/rate/<string:token>/submit_feedback"],
        type="http",
        auth="public",
        methods=["post", "get"],
        website=True,
    )
    def action_submit_rating(self, token, rate=0, **kwargs):

        rating, record_sudo = self._get_rating_and_record(token)

        if not self._has_rating_partner_access(rating):
            return self._render_invalid_partner_page(rating, record_sudo)

        # a rating given more than RATING_CHANGE_WINDOW ago is the customer's
        # last word: its link, forwarded or left in a mailbox, no longer
        # rewrites it in their name
        if request.httprequest.method == "POST" and rating._is_open_through_link():
            rate = int(rate)
            if rate not in (
                RATING_HAPPY_VALUE,
                RATING_NEUTRAL_VALUE,
                RATING_UNHAPPY_VALUE,
            ):
                raise ValueError(
                    f"Incorrect rating: should be {RATING_UNHAPPY_VALUE}, "
                    f"{RATING_NEUTRAL_VALUE} or {RATING_HAPPY_VALUE} (received {rate})"
                )
            record_sudo.rating_apply(
                rate,
                rating=rating,
                feedback=kwargs.get("feedback"),
                subtype_xmlid=None,  # force default subtype choice
            )
        return self._render_rating_page(rating)

    def _render_rating_page(self, rating):
        lang = rating.partner_id.lang or get_lang(request.env).code
        return (
            request.env["ir.ui.view"]
            .with_context(lang=lang)
            ._render_template(
                "rating.rating_external_page_view",
                {
                    "web_base_url": rating.get_base_url(),
                    "rating": rating,
                },
            )
        )

    def _has_rating_partner_access(self, rating) -> bool:
        return bool(
            request.env.user._is_public()
            or request.env.user.partner_id.commercial_partner_id
            == rating.partner_id.commercial_partner_id
        )

    def _render_invalid_partner_page(self, rating, record_sudo):
        return request.render(
            "rating.rating_external_page_invalid_partner",
            {
                "model_name": request.env["ir.model"]
                ._get(rating.res_model)
                .display_name,
                "name": record_sudo.display_name,
                "web_base_url": rating.get_base_url(),
            },
        )

    def _get_rating_and_record(self, token):
        try:
            rating_sudo = (
                request.env["access.link"]
                ._resolve(token, model="rating.rating", role="comment")
                .record
            )
        except LinkRefused, LinkLoginRequired:
            raise werkzeug.exceptions.NotFound from None

        record_sudo = (
            request.env[rating_sudo.res_model].sudo().browse(rating_sudo.res_id)
        )
        if not record_sudo.exists():
            raise werkzeug.exceptions.NotFound
        return rating_sudo, record_sudo
