from odoo.http import request, route
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads

from odoo.addons.calendar.controllers.booking import AppointmentController

_debug = DebugLog(__name__)


class AppointmentHr(AppointmentController):
    # ------------------------------------------------------------
    # APPOINTMENT TYPE PAGE VIEW
    # ------------------------------------------------------------

    @route()
    def appointment_type_page(self, appointment_type_id, state=False, **kwargs):

        if not kwargs.get("filter_staff_user_ids"):
            appointment_type = (
                request.env["appointment.type"].sudo().browse(int(appointment_type_id))
            )
            kwargs["filter_staff_user_ids"] = self._get_filtered_staff_user_ids(
                appointment_type,
                kwargs.get("filter_employee_ids"),
                kwargs.get("employee_id"),
            )
        return super().appointment_type_page(appointment_type_id, state, **kwargs)

    def _get_filtered_staff_user_ids(
        self, appointment_type, filter_employee_ids=None, employee_id=None
    ):
        """Return the suggested staff users, ensuring retrocompatibility with the
        deprecated employee-based route parameters. If several parameters are given,
        priority goes to the newest route format filter first.

        :return: string representation of a list of ``res.users`` ids, '[]' if none
        :rtype: str
        """

        # Ensure old link ?filter_employee_ids= retrocompatibility. This parameter is deprecated.
        filter_employee_ids = (
            json_loads(filter_employee_ids) if filter_employee_ids else []
        )
        if filter_employee_ids:
            employees = (
                request.env["hr.employee"].sudo().browse(filter_employee_ids).exists()
            )
            valid_employees = employees.filtered(
                lambda emp: emp.user_id in appointment_type.staff_user_ids
            )
            _debug.logic(
                "appointment_staff_filter",
                by="deprecated_filter_employee_ids",
                appointment_type=appointment_type,
                asked=len(filter_employee_ids),
                # an employee who is not a staff user of this appointment type
                # is dropped silently, and dropping all of them falls through
                # to the next branch rather than returning an empty filter
                valid=len(valid_employees),
            )
            if valid_employees:
                return str(valid_employees.user_id.ids)

        # Ensure old link ?employee_id= retrocompatibility. This parameter is deprecated.
        if employee_id:
            employee = request.env["hr.employee"].sudo().browse(int(employee_id))
            _debug.logic(
                "appointment_staff_filter",
                by="deprecated_employee_id",
                appointment_type=appointment_type,
                employee=employee_id,
                exists=bool(employee.exists()),
                is_staff=employee.user_id in appointment_type.staff_user_ids,
            )
            if (
                employee.exists()
                and employee.user_id in appointment_type.staff_user_ids
            ):
                return str(employee.user_id.ids)

        _debug.logic(
            "appointment_staff_filter",
            # the same empty filter for a deleted employee, one who is not
            # staff, and no parameter at all
            by="no_usable_parameter",
            appointment_type=appointment_type,
            had_filter_employee_ids=bool(filter_employee_ids),
            had_employee_id=bool(employee_id),
        )
        return "[]"
