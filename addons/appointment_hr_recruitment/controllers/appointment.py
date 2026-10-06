from odoo.http import request

from odoo.addons.calendar.controllers.booking import AppointmentController


class AppointmentHrRecruitmentController(AppointmentController):
    def _prepare_extra_calendar_event_vals(self, **kwargs):
        res = super()._prepare_extra_calendar_event_vals(**kwargs)
        if applicant_code := kwargs.get("applicant_code"):
            applicant_sudo = (
                request.env["hr.applicant"]
                .sudo()
                .search([("interview_invite_code", "=", applicant_code)], limit=1)
            )
            if applicant_sudo:
                res["applicant_id"] = applicant_sudo.id
        return res
