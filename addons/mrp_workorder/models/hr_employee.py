from datetime import datetime

from odoo import models
from odoo.http import request
from odoo.libs.debug_log import DebugLog

EMPLOYEES_CONNECTED = "employees_connected"
SESSION_OWNER = "session_owner"

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"


    def pin_validation(self, pin=False) -> bool:
        if not pin:
            pin = False
        return self.sudo().pin == pin

    def login(self, pin=False, set_in_session=True):
        if self.pin_validation(pin) and set_in_session:
            self._connect_employee()
            request.session[SESSION_OWNER] = self.id
            _debug.lifecycle("shopfloor_login", employee=self.id)
            return True
        _debug.logic(
            "shopfloor_login_refused",
            employee=self.id,
            by="pin" if set_in_session else "no_session",
        )
        return False

    def logout(self, pin=False, unchecked=False):
        employees = request.session.get(EMPLOYEES_CONNECTED, [])
        owner = request.session.get(SESSION_OWNER, False)
        if (self.pin_validation(pin) or unchecked) and self.id in employees:
            request.session[SESSION_OWNER] = self.id
            employees.remove(self.id)
            request.session[EMPLOYEES_CONNECTED] = employees
            if owner == self.id:
                owner = False
            request.session[SESSION_OWNER] = owner
            _debug.lifecycle(
                "shopfloor_logout", employee=self.id, remaining=len(employees)
            )
            return True
        _debug.logic("shopfloor_logout_refused", employee=self.id)
        return False

    def remove_session_owner(self) -> None:
        self.check_singleton()
        if self.id == request.session.get(SESSION_OWNER):
            request.session[SESSION_OWNER] = False

    def _get_employee_fields_for_tablet(self) -> list:
        return [
            "id",
            "name",
        ]

    def _connect_employee(self) -> None:
        employees = request.session.get(EMPLOYEES_CONNECTED, [])
        if len(employees) == 0:
            request.session[EMPLOYEES_CONNECTED] = [self.id]
            return
        if self.id not in employees:
            request.session[EMPLOYEES_CONNECTED] = [self.id] + employees

    def get_employees_wo_by_employees(self, employees_ids):
        employees = [{"id": id} for id in employees_ids]
        workorders = self.env["mrp.workorder"].search([("state", "=", "progress")])
        time_ids = self.env["mrp.workcenter.productivity"]._read_group(
            [
                "&",
                ("employee_id", "in", employees_ids),
                ("workorder_id", "in", workorders.ids),
            ],
            ["employee_id", "workcenter_id"],
            ["duration:sum", "date_end:array_agg", "date_start:array_agg"],
        )

        for emp in employees:
            emp["workcenters"] = []
        for employee, workcenter, duration, end_dates, start_dates in time_ids:
            for end_date, start_date in zip(end_dates, start_dates, strict=False):
                if not end_date:
                    duration += int((datetime.now() - start_date).total_seconds()) / 60
            employee = next(emp for emp in employees if emp["id"] == employee.id)
            if any(not date for date in end_dates):
                employee["workcenters"].append(
                    {
                        "id": workcenter.id,
                        "name": workcenter.name,
                        "duration": duration,
                        "ongoing": True,
                    }
                )
            else:
                employee["last_active"] = max(
                    employee.get("last_active", datetime.min),  # noqa: DTZ901 -- Odoo stores UTC datetimes without tzinfo; this is a naive bound.
                    *(d for d in end_dates if d),
                )
        return employees

    def get_wo_time_by_employees_ids(self, wo_id):
        time_ids = self.env["mrp.workcenter.productivity"].search(
            [("employee_id", "=", self.id), ("workorder_id", "=", wo_id)]
        )
        sum_time_seconds = 0
        for time in time_ids:
            if time.date_end:
                sum_time_seconds += (time.date_end - time.date_start).total_seconds()
            else:
                sum_time_seconds += int(
                    (datetime.now() - time.date_start).total_seconds()
                )
        return sum_time_seconds / 60

    def stop_all_workorder_from_employee(self) -> None:
        work_orders = self.env["mrp.workorder"].search(
            ["&", ("state", "=", "progress"), ("employee_ids.id", "in", self.ids)]
        )
        work_orders.stop_employee(self.ids)

    def get_employees_connected(self):
        if request:
            return request.session.get(EMPLOYEES_CONNECTED, [])
        else:
            return [self.env.user.employee_id.id]

    def set_employees_connected(self) -> None:
        new_employees = self
        old_employees = self.browse(request.session.get(EMPLOYEES_CONNECTED, []))
        (old_employees - new_employees).stop_all_workorder_from_employee()
        request.session[EMPLOYEES_CONNECTED] = new_employees.ids

    def get_session_owner(self):
        if request:
            return request.session.get(SESSION_OWNER, False)
        return self.env.user.employee_id.id

    def login_user_employee(self) -> None:
        if self.get_session_owner():
            return
        user_employee = self.env.user.employee_id
        if user_employee and user_employee.login():
            return
        for employee in self.get_employees_connected():
            if self.browse(employee).login():
                return
        if user_employee:
            user_employee._connect_employee()

    def get_all_employees(self, login=False):
        if login:
            self.login_user_employee()

        domain = [
            "|",
            ("company_id", "=", False),
            ("company_id", "in", self.env.companies.ids),
        ]
        all_employees = self.search_read(domain, fields=["id", "name"])

        all_employees_ids = {employee["id"] for employee in all_employees}
        employees_connected = list(
            filter(
                lambda employee_id: employee_id in all_employees_ids,
                self.get_employees_connected(),
            )
        )
        out = {
            "admin": self.get_session_owner(),
            "connected": self.get_employees_wo_by_employees(employees_connected),
        }
        if login:
            out["all"] = all_employees
        return out
