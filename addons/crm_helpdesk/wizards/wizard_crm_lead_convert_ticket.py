from odoo import Command, api, fields, models


class WizardCrmLeadConvertTicket(models.TransientModel):
    _name = "wizard.crm.lead.convert.ticket"
    _description = "Lead convert to Ticket"

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        if "partner_id" in fields:
            lead_id = result.get("lead_id")
            if lead_id:
                lead = self.env["crm.lead"].browse(lead_id)
                result["partner_id"] = lead._find_matching_partner().id
        if "team_id" in fields:
            team_ids = self.env["team.team"].search(
                [("use_helpdesk", "=", True)], limit=2
            )
            result["team_id"] = team_ids[0].id if len(team_ids) == 1 else None
        return result

    lead_id = fields.Many2one(
        comodel_name="crm.lead",
        default=lambda self: self.env.context.get("active_id", None),
        domain=[("type", "=", "lead")],
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        required=True,
        domain=[("use_helpdesk", "=", True)],
    )

    def action_lead_to_helpdesk_ticket(self) -> dict:
        self.check_singleton()
        lead = self.lead_id
        partner = self.partner_id
        if not partner and (lead.partner_name or lead.contact_name):
            lead._handle_partner_assignment(create_missing=True)
            partner = lead.partner_id

        vals = {
            "name": lead.name,
            "description": lead.description,
            "team_id": self.team_id.id,
            "partner_id": partner.id,
            "user_id": None,
            "campaign_id": lead.campaign_id.id,
            "medium_id": lead.medium_id.id,
            "source_id": lead.source_id.id,
        }
        if lead.contact_name:
            vals["partner_name"] = lead.contact_name
        vals["phone_ids"] = [Command.set((lead.phone_ids or partner.phone_ids).ids)]
        if lead.email_from:
            vals["partner_email"] = lead.email_from

        ticket_sudo = (
            self.env["helpdesk.ticket"]
            .with_context(mail_create_nosubscribe=True, mail_create_nolog=True)
            .sudo()
            .create(vals)
        )
        ticket_sudo.message_post_with_source(
            "mail.message_origin_link",
            render_values={"self": ticket_sudo, "origin": lead},
            subtype_xmlid="mail.mt_note",
        )

        lead.message_change_thread(ticket_sudo)
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", "crm.lead"), ("res_id", "=", lead.id)]
        )
        attachments.sudo().write(
            {"res_model": "helpdesk.ticket", "res_id": ticket_sudo.id}
        )
        lead._message_log(
            body=self.env._(
                "Lead converted into ticket %s", ticket_sudo._get_html_link()
            )
        )
        lead.action_archive()

        if not ticket_sudo.with_env(self.env).has_access("read"):
            return {
                "name": self.env._("Lead Converted"),
                "view_mode": "form",
                "res_model": lead._name,
                "type": "ir.actions.act_window",
                "res_id": lead.id,
            }

        view = self.env.ref("helpdesk.helpdesk_ticket_view_form")
        return {
            "name": self.env._("Ticket Created"),
            "view_mode": "form",
            "view_id": view.id,
            "res_model": "helpdesk.ticket",
            "type": "ir.actions.act_window",
            "res_id": ticket_sudo.id,
            "context": self.env.context,
        }
