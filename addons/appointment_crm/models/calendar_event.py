from markupsafe import Markup

from odoo import Command, api, fields, models


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    opportunity_id = fields.Many2one(
        compute="_compute_opportunity_id",
        store=True,
        readonly=False,
        tracking=True,
    )

    @api.depends("appointment_invite_id")
    def _compute_opportunity_id(self) -> None:
        for event in self:
            if event.appointment_invite_id.opportunity_id:
                event.opportunity_id = event.appointment_invite_id.opportunity_id

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        events.filtered(
            lambda e: (
                e.appointment_type_id.lead_create
                and e.partner_ids - e.user_id.partner_id
                and not e.opportunity_id
            )
        ).sudo()._create_lead_from_appointment()
        opportunity_field = self.env["ir.model.fields"]._get(
            "calendar.event", "opportunity_id"
        )
        for meeting in events.filtered("opportunity_id"):
            if not meeting.activity_ids:
                meeting.opportunity_id.sudo().activity_schedule(
                    act_type_xmlid="mail.mail_activity_data_meeting",
                    date_deadline=meeting._get_activity_deadline_from_start(
                        meeting.start, meeting.allday
                    ),
                    summary=meeting.name,
                    user_id=meeting.user_id.id,
                    calendar_event_id=meeting.id,
                )
            meeting._message_log(
                body=Markup("<p>%s</p>")
                % self.env._(
                    "Meeting linked to Lead/Opportunity %s",
                    meeting.opportunity_id._get_html_link(),
                ),
                tracking_value_ids=[
                    Command.create(
                        {
                            "field_id": opportunity_field.id,
                            "old_value_char": False,
                            "new_value_char": meeting.opportunity_id.name,
                        }
                    )
                ],
            )
        return events

    def _create_lead_from_appointment(self):
        lead_values = []
        for event in self:
            partner = event.partner_ids - event.user_id.partner_id
            lead_values.append(event._prepare_lead_vals(partner[:1]))

        leads = (
            self.env["crm.lead"]
            .with_context(mail_create_nosubscribe=True)
            .with_company(self.user_id.company_id)
            .create(lead_values)
        )
        for event, lead in zip(self, leads, strict=False):
            event._link_with_lead(lead)
        return leads

    def _prepare_lead_vals(self, partner):
        return {
            "name": self.name,
            "partner_id": partner.id,
            "type": "opportunity",
            "user_id": self.user_id.id,
            "description": self.description,
        }

    def _link_with_lead(self, lead) -> None:
        self.write(
            {
                "res_model_id": self.env["ir.model"]._get(lead._name).id,
                "res_id": lead.id,
                "opportunity_id": lead.id,
            }
        )
