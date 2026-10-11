from datetime import UTC, timedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import groupby

_debug = DebugLog(__name__)


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    work_hours_activated = fields.Boolean(string="Employee Schedule")

    def _get_default_range_slots(self, category):
        range_values = super()._get_default_range_slots(category)
        if category == "anytime" and self.work_hours_activated:
            range_values.update(hours_range=((0, 0),))
        return range_values

    def _slot_availability_is_user_available(
        self, slot, staff_user, availability_values, asked_capacity=1
    ):
        slot_start_dt_utc, slot_end_dt_utc = slot["UTC"][0], slot["UTC"][1]
        is_available = super()._slot_availability_is_user_available(
            slot, staff_user, availability_values, asked_capacity
        )
        if not is_available or not self.work_hours_activated:
            return is_available

        workhours = availability_values.get("work_schedules")
        _debug.logic(
            "appointment_work_hours_applied",
            appointment_type=self,
            user=staff_user,
            applied=workhours is not None and staff_user.partner_id in workhours,
            scheduled_users=len(workhours) if workhours is not None else 0,
        )
        if workhours is not None and staff_user.partner_id in workhours:
            is_available = self._slot_availability_is_user_working(
                slot_start_dt_utc, slot_end_dt_utc, workhours[staff_user.partner_id]
            )

        return is_available

    def _slot_availability_is_user_working(self, start_dt, end_dt, intervals) -> bool:

        def find_start_index():

            def recursive_find_index(lower_bound, upper_bound):
                if upper_bound - lower_bound <= 1:
                    if intervals[upper_bound][0] <= start_dt:
                        return upper_bound
                    return lower_bound
                index = (upper_bound + lower_bound) // 2
                if intervals[index][0] <= start_dt:
                    return recursive_find_index(index, upper_bound)
                return recursive_find_index(lower_bound, index)

            if start_dt <= intervals[0][0] - tolerance:
                return -1
            if end_dt >= intervals[-1][1] + tolerance:
                return -1
            return recursive_find_index(0, len(intervals) - 1)

        if not intervals:
            _debug.logic(
                "appointment_slot_unavailable",
                reason="employee_has_no_work_interval_in_the_window",
                start=start_dt,
                end=end_dt,
            )
            return False

        tolerance = timedelta(minutes=1)
        start_index = find_start_index()
        if start_index != -1:
            for index in range(start_index, len(intervals)):
                if intervals[index][1] >= end_dt - tolerance:
                    _debug.logic(
                        "appointment_slot_available",
                        start=start_dt,
                        end=end_dt,
                        interval=index,
                        intervals=len(intervals),
                    )
                    return True
                if (
                    len(intervals) == index + 1
                    or intervals[index + 1][0] - intervals[index][1] > tolerance
                ):
                    _debug.logic(
                        "appointment_slot_unavailable",
                        reason="work_day_ends_before_the_slot"
                        if len(intervals) == index + 1
                        else "gap_between_work_intervals",
                        start=start_dt,
                        end=end_dt,
                        interval=index,
                    )
                    return False
        _debug.logic(
            "appointment_slot_unavailable",
            reason="slot_lies_outside_every_work_interval"
            if start_index == -1
            else "scan_ran_off_the_end",
            start=start_dt,
            end=end_dt,
            intervals=len(intervals),
        )
        return False

    def _slot_availability_prepare_users_values(self, staff_users, start_dt, end_dt):
        values = super()._slot_availability_prepare_users_values(
            staff_users, start_dt, end_dt
        )
        values.update(
            self._slot_availability_prepare_users_values_workhours(
                staff_users, start_dt.astimezone(UTC), end_dt.astimezone(UTC)
            )
        )
        return values

    @api.model
    def _slot_availability_prepare_users_values_workhours(
        self, staff_users, start_dt, end_dt
    ) -> dict:
        if self.category == "custom" or not self.work_hours_activated:
            _debug.logic(
                "appointment_work_schedules_skipped",
                appointment_type=self,
                reason="custom_category"
                if self.category == "custom"
                else "work_hours_not_activated",
                users=len(staff_users),
            )
            return {"work_schedules": {}}

        users_to_employees = dict(
            groupby(staff_users.sudo().employee_id, lambda employee: employee.user_id)
        )
        users_with_no_employees = staff_users.sudo().filtered(
            lambda user: user not in users_to_employees
        )
        if users_with_no_employees:
            users_to_employees.update(
                groupby(
                    self.env["hr.employee"]
                    .with_context(
                        allowed_company_ids=self.env["res.company"]
                        .sudo()
                        .search([])
                        .ids
                    )
                    .sudo()
                    .search([("user_id", "in", users_with_no_employees.ids)]),
                    lambda employee: employee.user_id,
                )
            )
        strict_schedule_employees = (
            self.env["hr.employee"]
            .sudo()
            .union(
                *(
                    employees[0]
                    for employees in users_to_employees.values()
                    if employees
                    and employees[0].resource_calendar_id
                    and employees[0].resource_calendar_id.schedule_type != "flexible"
                )
            )
        )

        if _debug.pipeline.enabled:
            _debug.pipeline(
                "appointment_work_schedules_scope",
                appointment_type=self,
                users=len(staff_users),
                users_without_employee=len(users_with_no_employees),
                with_strict_schedule=len(strict_schedule_employees),
                resolved=len(users_to_employees),
            )
        if not strict_schedule_employees:
            return {"work_schedules": {}}

        work_intervals, _calendar_intervals = (
            strict_schedule_employees.resource_id._get_valid_work_intervals(
                start_dt, end_dt
            )
        )
        work_schedules = {
            employee.partner_id: [
                (
                    interval_start.astimezone(UTC).replace(tzinfo=None),
                    interval_stop.astimezone(UTC).replace(tzinfo=None),
                )
                for interval_start, interval_stop, _meta in work_intervals[
                    employee.resource_id.id
                ]
            ]
            for employee in strict_schedule_employees
        }

        _debug.pipeline(
            "appointment_work_schedules",
            appointment_type=self,
            start=start_dt,
            end=end_dt,
            calendars=len(strict_schedule_employees.resource_calendar_id),
            partners=len(work_schedules),
        )
        return {"work_schedules": work_schedules}
