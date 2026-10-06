from odoo import api, fields, models


class CalendarAlarm(models.Model):
    _inherit = "calendar.alarm"

    alarm_type = fields.Selection(
        selection_add=[("whatsapp", "WhatsApp Message")],
        ondelete={"whatsapp": "set default"},
    )
    wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="WhatsApp Template",
        compute="_compute_wa_template_id",
        store=True,
        readonly=False,
        domain=[("model", "=", "calendar.attendee"), ("status", "=", "approved")],
        help="Template used to render WhatsApp reminder content.",
    )

    @api.model
    def _get_responsible_aware_alarm_types(self):
        # `whatsapp_calendar._send_reminder` filters out the event organizer
        # unless this flag is set, so it is meaningful for this type.
        return super()._get_responsible_aware_alarm_types() | {"whatsapp"}

    @api.depends("alarm_type")
    def _compute_wa_template_id(self) -> None:
        self.filtered(lambda a: a.alarm_type != "whatsapp").wa_template_id = False
