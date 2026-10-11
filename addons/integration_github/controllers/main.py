from odoo import http
from odoo.http import request

from ..models.integration_github_webhook import EVENT_HEADER, WEBHOOK_ROUTE


class GithubWebhookController(http.Controller):
    @http.route(
        f"{WEBHOOK_ROUTE}<string:hook_uuid>",
        type="http",
        auth="receiver",
        receiver="integration.github.webhook:hook_uuid",
        receiver_event="github",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def webhook(self, hook_uuid: str) -> http.Response:
        admission = request.admission
        event = request.httprequest.headers.get(EVENT_HEADER, "")
        if event:
            admission.retag(event)
        outcome = admission.subject._dispatch(event, admission.json())
        return request.prepare_json_response({"event": event, "outcome": outcome})
