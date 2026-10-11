from odoo import Command, api, fields, models


class WizardCalendarEventDelete(models.TransientModel):
    _name = "wizard.calendar.event.delete"
    _inherit = ["mixin.mail.composer"]
    _description = "Calendar Popover Delete Wizard"

    calendar_event_id = fields.Many2one(comodel_name="calendar.event")
    delete = fields.Selection(
        selection=[
            ("one", "Delete this event"),
            ("next", "Delete this and following events"),
            ("all", "Delete all the events"),
        ],
        default="one",
    )
    recipient_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Recipients",
        compute="_compute_recipient_ids",
        readonly=False,
    )

    def close(self):
        self.check_singleton()
        event = self.calendar_event_id
        organizer_is_sole_attendee = (
            event.attendee_ids.partner_id == event.user_id.partner_id
        )
        if organizer_is_sole_attendee:
            event._unlink_by_recurrence_policy(self.delete)
            return None
        return event.action_unlink_event(self.delete)

    @api.depends("calendar_event_id")
    def _compute_recipient_ids(self) -> None:
        for wizard in self:
            wizard.recipient_ids = (
                wizard.calendar_event_id.partner_id
                | wizard.calendar_event_id.attendee_ids.partner_id
            )

    @api.depends("calendar_event_id")
    def _compute_subject(self) -> None:
        for wizard in self.filtered("template_id"):
            wizard.subject = wizard.template_id._render_field(
                "subject",
                [wizard.calendar_event_id.id],
                compute_lang=True,
                options={"post_process": True},
            )[wizard.calendar_event_id.id]

    @api.depends("calendar_event_id")
    def _compute_body(self) -> None:
        for wizard in self.filtered("template_id"):
            wizard.body = wizard.template_id._render_field(
                "body_html",
                [wizard.calendar_event_id.id],
                compute_lang=True,
                options={"post_process": True},
            )[wizard.calendar_event_id.id]

    def action_delete(self) -> dict | None:
        self.check_singleton()
        self.calendar_event_id._unlink_by_recurrence_policy(
            self.env.context.get("default_recurrence")
        )

        return {"type": "ir.actions.act_url", "target": "self", "url": "/odoo/calendar"}

    def action_send_mail_and_delete(self):
        self.env.ref("calendar.calendar_template_delete_event").send_mail(
            self.calendar_event_id.id,
            email_layout_xmlid="mail.mail_notification_light",
            force_send=True,
            email_values={
                "subject": self.subject,
                "body_html": self.body,
                "partner_ids": [Command.set(self.recipient_ids.ids)],
            },
        )
        return self.action_delete()
