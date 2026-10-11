from odoo import Command, models, tools


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _find_matching_partner(
        self, email_only=False, force_create=False, force_update=True
    ):
        self.check_singleton()
        partner = self.partner_id

        if not partner and self.email_cc:
            partner = self.env["res.partner"].search(
                [("email_normalized", "=", tools.email_normalize(self.email_cc))],
                limit=1,
            )
        elif self.phone_ids:
            partner = self.env["res.partner"].search(
                [("phone_ids", "in", self.phone_ids.ids)], limit=1
            )

        if not partner and force_create:
            partner = self.env["res.partner"].create(
                {
                    "name": self.partner_name or self.name,
                    "email": self.partner_name or self.email_cc,
                    "phone_ids": [Command.set(self.phone_ids.ids)],
                }
            )

        if partner and force_update:
            if not partner.email and self.partner_email:
                partner.email = self.partner_email
            if not partner.phone_ids and self.phone_ids:
                partner.phone_ids = self.phone_ids

        return partner

    def action_convert_ticket_to_lead_or_opportunity(self) -> dict:
        return {
            "name": self.env._("Convert to Lead")
            if self.env.user.has_group("crm.group_use_lead")
            else self.env._("Convert to Opportunity"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.helpdesk.ticket.convert.lead",
            "view_mode": "form",
            "view_id": self.env.ref(
                "crm_helpdesk.helpdesk_ticket_to_lead_view_form"
            ).id,
            "target": "new",
            "context": {
                "dialog_size": "medium",
            },
        }
