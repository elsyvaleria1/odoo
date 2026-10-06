from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    attendance_count = fields.Integer(compute="_compute_attendance_count")

    def _get_attendance_by_payslip(self):
        """
        Find all attendances linked to payslips.

        Note: An attendance is linked to a payslip if it has
        the same employee and the time periods correspond.

        :return: dict with:
                    - key = payslip record
                    - value = attendances recordset linked to payslip
        """
        attendance_by_payslip = defaultdict(lambda: self.env["hr.attendance"])
        slip_by_employee = defaultdict(lambda: self.env["hr.payslip"])
        attendance_domains = []
        for slip in self:
            if slip.version_id.work_entry_source != "attendance":
                continue
            slip_by_employee[slip.employee_id.id] |= slip
            attendance_domains.append(
                [
                    ("employee_id", "=", slip.employee_id.id),
                    ("check_in", "<=", slip.date_to),
                    ("check_out", ">=", slip.date_from),
                ]
            )
        attendance_group = self.env["hr.attendance"]._read_group(
            Domain.OR(attendance_domains),
            groupby=["employee_id", "check_in:day", "check_out:day"],
            aggregates=["id:recordset"],
        )
        _debug.perf.count(
            "attendance_by_payslip",
            payslips=self,
            attendance_sourced=len(attendance_domains),
            groups=len(attendance_group),
        )
        for employee, check_in, check_out, attendance in attendance_group:
            for slip in slip_by_employee[employee.id]:
                # Overlap test on both ends, mirroring the domain above: an
                # attendance whose check_in is before the period but whose
                # check_out still falls inside it (e.g. an overnight shift
                # starting the day before) must not be dropped.
                if (
                    slip.date_from <= check_out.date()
                    and check_in.date() <= slip.date_to
                ):
                    attendance_by_payslip[slip] |= attendance
        return attendance_by_payslip

    @api.depends("date_from", "date_to", "version_id", "version_id.work_entry_source")
    def _compute_attendance_count(self) -> None:
        attendance_by_payslip = self._get_attendance_by_payslip()
        for slip in self:
            slip.attendance_count = len(attendance_by_payslip[slip])

    def action_view_attendances(self) -> dict:
        self.check_singleton()
        attendance = self._get_attendance_by_payslip()[self]
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Attendances"),
            "res_model": "hr.attendance",
            "views": [[False, "list"]],
            "context": {"create": 0},
            "domain": [("id", "in", attendance.ids)],
        }
