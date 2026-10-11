from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools.date_utils import get_timedelta, time_unit_selection


class MixinEventMailSchedule(models.AbstractModel):

    _name = "mixin.event.mail.schedule"
    _description = "Event Communication Scheduling"

    interval_nbr = fields.Integer(
        string="Interval",
        default=1,
    )
    interval_unit = fields.Selection(
        selection=[
            ("now", "Immediately"),
            *time_unit_selection("hour", "day", "week", "month"),
        ],
        string="Unit",
        default="hour",
        required=True,
    )
    interval_type = fields.Selection(
        selection=[
            ("after_sub", "After each registration"),
            ("before_event", "Before the event starts"),
            ("after_event_start", "After the event started"),
            ("after_event", "After the event ended"),
            ("before_event_end", "Before the event ends"),
        ],
        string="Trigger",
        default="before_event",
        required=True,
        help="Indicates when the communication is sent. "
        "If the event has multiple slots, the interval is related to each time slot instead of the whole event.",
    )
    notification_type = fields.Selection(
        selection=[("mail", "Mail")],
        string="Send",
        compute="_compute_notification_type",
    )
    template_ref = fields.Reference(
        selection=[("mail.template", "Mail")],
        string="Template",
        required=True,
        ondelete={"mail.template": "cascade"},
    )

    @api.depends("template_ref")
    def _compute_notification_type(self) -> None:
        self.notification_type = "mail"

    def _template_model_by_notification_type(self):
        return {
            "mail": "mail.template",
        }

    def _prepare_event_mail_values(self) -> dict:
        self.check_singleton()
        return {
            "interval_nbr": self.interval_nbr,
            "interval_unit": self.interval_unit,
            "interval_type": self.interval_type,
            "template_ref": f"{self.template_ref._name},{self.template_ref.id}",
        }

    def _get_schedule_delta(self, count):
        self.check_singleton()
        if self.interval_unit == "now":
            return relativedelta()
        return get_timedelta(count, self.interval_unit)
