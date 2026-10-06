import uuid

from odoo import fields, models
from odoo.http import request

from odoo.addons.calendar.controllers.booking_calendar_view import (
    AppointmentCalendarView,
)


class Applicant(models.Model):
    _inherit = "hr.applicant"

    interview_invite_code = fields.Char(
        compute="_compute_interview_invite_code",
        precompute=True,
        store=True,
        copy=False,
        readonly=True,
    )

    def _compute_interview_invite_code(self) -> None:
        for app in self.filtered(lambda app: not app.interview_invite_code):
            app.interview_invite_code = uuid.uuid4().hex[:16]

    def action_create_meeting(self):
        res = super().action_create_meeting()
        if self.interview_invite_code:
            res["context"]["applicant_code"] = self.interview_invite_code
        return res

    def _get_interview_invite_url(self):
        self.check_singleton()
        if not request:
            return ""

        return AppointmentCalendarView._appointment_type_search_create_anytime(
            context={**self.env.context, "applicant_code": self.interview_invite_code},
            user=self.user_id,
        )["invite_url"]
