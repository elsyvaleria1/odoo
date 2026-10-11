from datetime import datetime

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _get_employee_calendar(self, version=None):
        self.check_singleton()
        contracts = (
            self.employee_id.sudo()._get_versions_with_contract_overlap_with_period(
                self.check_in.date(), (self.check_out or self.check_in).date()
            )
        )
        if contracts:
            return contracts[0].resource_calendar_id
        return super()._get_employee_calendar(version)

    def _create_work_entries(self) -> None:
        work_entries_vals_list = []
        for attendance in self:
            if not attendance.check_out:
                _debug.logic(
                    "work_entry_skipped",
                    reason="attendance_open",
                    attendance=attendance,
                )
                continue
            contracts = attendance.employee_id.sudo()._get_versions_with_contract_overlap_with_period(
                attendance.check_in.date(), attendance.check_out.date()
            )
            for contract in contracts:
                if (
                    attendance.check_out > contract.date_generated_from
                    and attendance.check_in < contract.date_generated_to
                ):
                    work_entries_vals_list += contract._prepare_work_entries_values(
                        attendance.check_in, attendance.check_out
                    )

        if work_entries_vals_list:
            work_entries_vals_list = self.env[
                "hr.version"
            ]._generate_work_entries_postprocess(work_entries_vals_list)
            new_work_entries = (
                self.env["hr.work.entry"].sudo().create(work_entries_vals_list)
            )
            _debug.lifecycle(
                "work_entries_from_attendance",
                attendances=self,
                entries=new_work_entries,
            )
            if new_work_entries:
                start = min(
                    (a.check_in.date() for a in self if a.check_in), default=False
                )
                stop = max(
                    (a.check_out.date() for a in self if a.check_out), default=False
                )
                work_entry_groups = (
                    self.env["hr.work.entry"]
                    .sudo()
                    ._read_group(
                        [
                            ("date", "<=", stop),
                            ("date", ">=", start),
                            ("employee_id", "in", self.employee_id.ids),
                        ],
                        ["employee_id"],
                        ["id:recordset"],
                    )
                )
                work_entries_by_employee = {
                    employee.id: records for employee, records in work_entry_groups
                }

                included = self.env["hr.work.entry"]
                overlappping = self.env["hr.work.entry"]
                for work_entries in work_entries_by_employee.values():
                    new_employee_work_entries = work_entries & new_work_entries
                    previous_employee_work_entries = work_entries - new_work_entries
                    previous_employee_work_entries = (
                        previous_employee_work_entries.filtered(
                            lambda w: not w.attendance_id or w.attendance_id in self
                        )
                    )

                    attendance_intervals = new_employee_work_entries._to_intervals()
                    conflicts_intervals = previous_employee_work_entries._to_intervals()

                    outside_intervals = conflicts_intervals - attendance_intervals

                    overlappping |= self.env["hr.work.entry"]._from_intervals(
                        outside_intervals
                    )
                    included |= previous_employee_work_entries - overlappping
                overlappping.sudo().write({"attendance_id": False})
                included.sudo().write({"active": False})

    @api.model_create_multi
    def create(self, vals_list):
        start_dates = [v.get("check_in") for v in vals_list if v.get("check_in")]
        stop_dates = [v.get("check_out") for v in vals_list if v.get("check_out")]
        res = super().create(vals_list)
        with self.env["hr.work.entry"]._error_checking(
            start=min(start_dates, default=False),
            stop=max(stop_dates, default=False),
            employee_ids=res.employee_id.ids,
        ):
            res._create_work_entries()
        return res

    def write(self, vals):
        validated_work_entries = (
            self.env["hr.work.entry"]
            .sudo()
            .search([("attendance_id", "in", self.ids), ("state", "=", "validated")])
        )
        if validated_work_entries:
            _debug.logic(
                "attendance_write_refused",
                reason="validated_work_entry",
                attendances=self,
                entries=validated_work_entries,
            )
            raise UserError(
                self.env._(
                    "This attendance record is linked to a validated working entry. You can't modify it."
                )
            )
        new_check_out = vals.get("check_out")
        open_attendances = (
            self.filtered(lambda a: not a.check_out)
            if new_check_out
            else self.env["hr.attendance"]
        )
        skip_regenerate = bool(open_attendances) and open_attendances == self
        regenerate = (
            bool({"check_out", "check_in", "employee_id"} & vals.keys())
            and not skip_regenerate
        )
        old_slots = (
            {(attendance.date, attendance.employee_id.id) for attendance in self}
            if regenerate
            else set()
        )
        res = super().write(vals)
        if regenerate:
            new_slots = {
                (attendance.date, attendance.employee_id.id) for attendance in self
            }
            slot_pairs = old_slots | new_slots
            slots = [
                {"date": date, "employee_id": employee_id}
                for date, employee_id in slot_pairs
            ]
            self.env["wizard.hr.work.entry.regenerate"].sudo().regenerate_work_entries(
                slots=slots
            )
        if not open_attendances:
            return res
        start = min(
            self.mapped("check_in")
            + [Datetime.from_string(vals.get("check_in", False)) or datetime.max]
        )
        stop = max(
            self.mapped("check_out")
            + [Datetime.from_string(vals.get("check_out", False)) or datetime.min]
        )
        with self.env["hr.work.entry"]._error_checking(
            start=start, stop=stop, employee_ids=self.employee_id.ids
        ):
            open_attendances._create_work_entries()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_validated_work_entries(self) -> None:
        validated_work_entries = (
            self.env["hr.work.entry"]
            .sudo()
            .search([("attendance_id", "in", self.ids), ("state", "=", "validated")])
        )
        if validated_work_entries:
            _debug.logic(
                "attendance_unlink_refused",
                reason="validated_work_entry",
                attendances=self,
                entries=validated_work_entries,
            )
            raise UserError(
                self.env._(
                    "This attendance record is linked to a validated working entry. You can't delete it."
                )
            )

    def unlink(self):
        _debug.lifecycle("attendance_unlink", attendances=self)
        slots = [
            {"date": attendance.date, "employee_id": attendance.employee_id.id}
            for attendance in self
        ]
        start_dates = [a.check_in for a in self if a.check_in]
        stop_dates = [a.check_out for a in self if a.check_out]
        with self.env["hr.work.entry"]._error_checking(
            start=min(start_dates, default=False),
            stop=max(stop_dates, default=False),
            employee_ids=self.employee_id.ids,
        ):
            res = super().unlink()
        if slots:
            self.env["wizard.hr.work.entry.regenerate"].sudo().regenerate_work_entries(
                slots=slots
            )
        return res
