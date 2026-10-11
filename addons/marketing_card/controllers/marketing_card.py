import base64
from urllib.parse import quote

from werkzeug.exceptions import BadRequest

from odoo.http import Controller, prepare_content_disposition_header, request, route

SOCIAL_NETWORK_USER_AGENTS = (
    "Facebot",
    "facebookexternalhit",
    "Twitterbot",
    "LinkedInBot",
    "WhatsApp",
    "Pinterest",
    "Pinterestbot",
)


def _is_crawler(request) -> bool:
    return any(
        short_crawler_name in request.httprequest.user_agent.string
        for short_crawler_name in SOCIAL_NETWORK_USER_AGENTS
    )


def _get_card_from_url(card_id, card_slug):
    if card_slug:
        card_id = request.env["ir.http"]._unslug(card_slug)[1]
    if not card_id:
        raise request.prepare_not_found_error()
    card = request.env["card.card"].browse(card_id).exists()
    if not card:
        raise BadRequest
    return card


class MarketingCardController(Controller):
    @route(
        [
            "/cards/<string:card_slug>/card.jpg",
            "/cards/<int:card_id>/card.jpg",
        ],
        type="http",
        auth="public",
        sitemap=False,
        website=True,
    )
    def card_campaign_image(self, card_id=None, card_slug=None):
        card = _get_card_from_url(card_id, card_slug)
        if _is_crawler(request) and card.share_status != "shared":
            card.sudo().share_status = "shared"
        if not card.image:
            raise request.prepare_not_found_error()

        image_bytes = base64.b64decode(card.image)
        return request.prepare_response(
            image_bytes,
            [
                ("Content-Type", " image/jpeg"),
                ("Content-Length", len(image_bytes)),
                ("Content-Disposition", prepare_content_disposition_header("card.jpg")),
            ],
        )

    @route(
        [
            "/cards/<string:card_slug>/preview",
            "/cards/<int:card_id>/preview",
        ],
        type="http",
        auth="public",
        sitemap=False,
        website=True,
    )
    def card_campaign_preview(self, card_id=None, card_slug=None):
        card = _get_card_from_url(card_id, card_slug)
        if not card.share_status:
            card.sudo().share_status = "visited"

        campaign_sudo = card.sudo().campaign_id
        return request.render(
            "marketing_card.card_campaign_preview",
            {
                "card": card,
                "campaign": campaign_sudo,
                "quote": quote,
            },
        )

    @route(
        [
            "/cards/<string:card_slug>/redirect",
            "/cards/<int:card_id>/redirect",
        ],
        type="http",
        auth="public",
        sitemap=False,
        website=True,
    )
    def card_campaign_redirect(self, card_id=None, card_slug=None):
        card = _get_card_from_url(card_id, card_slug)

        campaign_sudo = card.sudo().campaign_id
        redirect_url = campaign_sudo.target_url or campaign_sudo.get_base_url()
        if card.active:
            redirect_url = campaign_sudo.link_tracker_id.short_url or redirect_url

        if _is_crawler(request):
            return request.render(
                "marketing_card.card_campaign_crawler",
                {
                    "image_url": card._get_card_url(),
                    "post_text": campaign_sudo.post_suggestion,
                    "post_suggestion": campaign_sudo.post_suggestion,
                    "target_name": card.display_name or "",
                },
            )

        return request.redirect(redirect_url)
