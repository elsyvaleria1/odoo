from odoo import models


class HrAttendanceOvertimeLine(models.Model):
    _name = "hr.attendance.overtime.line"
    _inherit = "hr.attendance.overtime.line"

    def action_approve(self):
        super().action_approve()
        self._update_related_work_entries()

    def action_refuse(self):
        super().action_refuse()
        self._update_related_work_entries()

    def _update_related_work_entries(self) -> None:
        related_attendances = self._linked_attendances()
        if not related_attendances:
            return
        related_work_entries = (
            self.env["hr.work.entry"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", related_attendances.employee_id.ids),
                    ("date", "<=", max(related_attendances.mapped("check_out")).date()),
                    ("date", ">=", min(related_attendances.mapped("check_in")).date()),
                ]
            )
        )
        if not related_work_entries:
            return
        slots = [
            {"date": attendance.date, "employee_id": attendance.employee_id.id}
            for attendance in related_attendances
        ]
        self.env["wizard.hr.work.entry.regenerate"].sudo().regenerate_work_entries(
            slots=slots
        )
