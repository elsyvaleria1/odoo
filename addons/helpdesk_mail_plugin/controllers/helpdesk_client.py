from odoo import http
from odoo.http import request
from odoo.tools import html2plaintext


class HelpdeskClientController(http.Controller):
    @http.route(
        "/mail_plugin/ticket/create",
        type="jsonrpc",
        auth="bearer",
        scope="odoo.plugin.outlook",
        cors="*",
        typed=True,
    )
    def helpdesk_ticket_create(
        self, partner_id: int, email_body: str, email_subject: str
    ):
        partner = request.env["res.partner"].browse(partner_id).exists()
        if not partner:
            return {"error": "partner_not_found"}

        record = (
            request.env["helpdesk.ticket"]
            .with_company(partner.company_id)
            .create(
                {
                    "name": html2plaintext(email_subject),
                    "partner_id": partner_id,
                    "description": email_body,
                    "user_id": request.env.uid,
                    "team_id": request.env["helpdesk.ticket"]._default_team_id(),
                }
            )
        )

        return {"ticket_id": record.id}
