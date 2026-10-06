from datetime import datetime

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _get_employee_calendar(self, version=None):
        """A contract's own schedule outranks the version's, when there is one.

        `version` is threaded through from `hr.attendance._schedule_version()`
        so the whole of one attendance resolves against one `hr.version`, and
        the base is not asked to recompute the fixed point this override was
        already handed. Dropping the parameter raises `TypeError` -- an
        override with the old arity shadows the base for every caller.
        """
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
        # Upon creating or closing an attendance, create the work entry directly if the attendance
        # was created within an already generated period
        # This code assumes that attendances are not created/written in big batches
        work_entries_vals_list = []
        for attendance in self:
            # Work entries need a check-out to compute a duration, skip attendances still open
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
                # Fetch overlapping work entries, grouped by employees
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

                # Archive work entries included in new work entries
                included = self.env["hr.work.entry"]
                overlappping = self.env["hr.work.entry"]
                for work_entries in work_entries_by_employee.values():
                    # Work entries for this employee
                    new_employee_work_entries = work_entries & new_work_entries
                    previous_employee_work_entries = work_entries - new_work_entries
                    # Our work entries are date+duration, so _to_intervals() is
                    # day-granular and every previous same-day entry would land
                    # in `included` below and be archived. An entry backed by a
                    # different attendance records real presence the new vals
                    # do not cover: keep it. Entries for self's own attendances
                    # (stale spans being re-closed) and unlinked ones still
                    # compete as before.
                    previous_employee_work_entries = (
                        previous_employee_work_entries.filtered(
                            lambda w: not w.attendance_id or w.attendance_id in self
                        )
                    )

                    # Convert to intervals so overlapping work entries can be diffed below
                    attendance_intervals = new_employee_work_entries._to_intervals()
                    conflicts_intervals = previous_employee_work_entries._to_intervals()

                    # Compute intervals completely outside any attendance
                    # Intervals are outside, but associated records are overlapping.
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
        # Closing every attendance touched by this write for the first time is
        # already handled directly and correctly by open_attendances._create_work_entries()
        # below. Running the full regeneration wizard on top of it only duplicates
        # that work: it creates a work entry that _create_work_entries() then
        # immediately cancels as an overlap, doubling writes for every clock-out.
        skip_regenerate = bool(open_attendances) and open_attendances == self
        # Key presence, not value truthiness: clearing check_out (reopening a
        # closed attendance) must regenerate too, or the work entry of the old
        # closed span stays active while the attendance is open-ended.
        regenerate = (
            bool({"check_out", "check_in", "employee_id"} & vals.keys())
            and not skip_regenerate
        )
        # Capture the pre-write (date, employee) pairs: if this write moves an
        # attendance to a different calendar day, or reassigns it to a
        # different employee, self.mapped('date')/self.employee_id below only
        # see the new day/employee once super().write() has run, and the old
        # day's or old employee's work entry would never be included in the
        # regeneration.
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
            + [Datetime.from_string(vals.get("check_in", False)) or datetime.max]  # noqa: DTZ901  naive sentinel compared against naive ORM datetimes
        )
        stop = max(
            self.mapped("check_out")
            + [Datetime.from_string(vals.get("check_out", False)) or datetime.min]  # noqa: DTZ901  naive sentinel compared against naive ORM datetimes
        )
        # No `skip=`: the early return above means this line is only reached
        # when `check_out` is in `vals`, so the flag that used to be computed
        # here could only ever be False -- which is also the parameter's
        # default.
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
        # Archive linked work entries upon deleting last attendance linked to the work entries.
        # Build slots from self's own (date, employee_id) pairs rather than searching
        # hr.work.entry with a Domain(employee_id in ...) AND Domain(date in ...): that
        # cross-products two independently-collected id/date lists, so a batch spanning
        # more than one employee and more than one day can match an unrelated employee's
        # unrelated day and needlessly regenerate it.
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
