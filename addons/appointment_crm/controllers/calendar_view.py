from odoo.fields import Domain
from odoo.http import request

from odoo.addons.calendar.controllers.booking_calendar_view import (
    AppointmentCalendarView,
)


class AppointmentCrmCalendarView(AppointmentCalendarView):
    @classmethod
    def _get_domain_staff_user_appointment_invite(cls, appointment_type, user):
        domain = super()._get_domain_staff_user_appointment_invite(
            appointment_type, user
        )
        if "default_opportunity_id" in request.env.context:
            domain = Domain.AND(
                [
                    domain,
                    [
                        (
                            "opportunity_id",
                            "=",
                            request.env.context["default_opportunity_id"],
                        )
                    ],
                ]
            )
        return domain
