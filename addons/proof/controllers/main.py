from urllib.parse import urlencode

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class ProofAnswer(http.Controller):
    @http.route(
        "/proof/answer/<int:delivery_id>",
        type="http",
        auth="link",
        link="proof.delivery:delivery_id",
        methods=["GET"],
        sitemap=False,
        website=True,
    )
    def proof_answer(self, delivery_id, error=None, **kwargs):
        delivery = request.link_subject
        challenge = delivery.challenge_id
        if challenge.partner_id.lang:
            request.update_context(lang=challenge.partner_id.lang)
        return request.render(
            "proof.proof_answer_page",
            {
                "delivery": delivery,
                "challenge": challenge,
                "open": delivery.state == "sent" and challenge.state == "issued",
                "access_token": kwargs.get("access_token"),
                "error": error,
            },
        )

    # a POST, never the GET: a mail scanner that opens the link to check it
    # must not answer for the contact
    @http.route(
        "/proof/answer/<int:delivery_id>/submit",
        type="http",
        auth="link",
        link="proof.delivery:delivery_id",
        link_role="comment",
        methods=["POST"],
        sitemap=False,
        website=True,
    )
    def proof_answer_submit(self, delivery_id, verdict="", reason="", **kwargs):
        delivery = request.link_subject
        params = {"access_token": kwargs.get("access_token", "")}
        try:
            delivery._answer(verdict, reason=reason)
        except UserError:
            params["error"] = 1
        return request.redirect(f"/proof/answer/{delivery.id}?{urlencode(params)}")
