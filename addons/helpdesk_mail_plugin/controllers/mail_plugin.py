from odoo.http import request

from odoo.addons.mail_plugin.controllers import mail_plugin


class MailPluginController(mail_plugin.MailPluginController):
    def _get_contact_data(self, partner):
        contact_values = super()._get_contact_data(partner)

        if not request.env["helpdesk.ticket"].has_access("create"):
            return contact_values

        contact_values["tickets"] = (
            self._get_partner_tickets(partner) if partner else []
        )

        return contact_values

    def _get_partner_tickets(self, partner, offset=0, limit=5):
        tickets = request.env["helpdesk.ticket"].search(
            [
                ("partner_id", "=", partner.id),
                ("stage_id.fold", "=", False),
            ],
            offset=offset,
            limit=limit,
        )

        if len(tickets) < limit:
            remaining = limit - len(tickets)
            folded_tickets = request.env["helpdesk.ticket"].search(
                [
                    ("partner_id", "=", partner.id),
                    ("stage_id.fold", "=", True),
                ],
                limit=remaining,
            )
            tickets |= folded_tickets

        return [
            {
                "ticket_id": ticket.id,
                "name": ticket.display_name,
                "fold": ticket.stage_id.fold,
            }
            for ticket in tickets
        ]

    def _mail_content_logging_models_whitelist(self):
        models_whitelist = super()._mail_content_logging_models_whitelist()
        if not request.env["helpdesk.ticket"].has_access("create"):
            return models_whitelist
        return models_whitelist + ["helpdesk.ticket"]

    def _translation_modules_whitelist(self):
        modules_whitelist = super()._translation_modules_whitelist()
        if not request.env["helpdesk.ticket"].has_access("create"):
            return modules_whitelist
        return modules_whitelist + ["helpdesk_mail_plugin"]
