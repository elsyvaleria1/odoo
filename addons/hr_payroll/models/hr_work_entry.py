from collections import defaultdict
from datetime import date, datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.datetime import timezone
from odoo.libs.intervals import Intervals


class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"
    has_payslip = fields.Boolean(compute="_compute_has_payslip")

    @api.depends("state")
    def _compute_has_payslip(self) -> None:
        all_payslips = self.env["hr.payslip"].search(
            [
                ("employee_id", "in", self.employee_id.ids),
                ("state", "in", ["validated", "paid"]),
                ("date_from", "<=", max(self.mapped("date"))),
                ("date_to", ">=", min(self.mapped("date"))),
            ]
        )

        for work_entry in self:
            work_entry.has_payslip = any(
                slip.employee_id == work_entry.employee_id
                and slip.date_from <= work_entry.date <= slip.date_to
                and not slip.is_refunded
                for slip in all_payslips
            )

    def _check_undefined_slots(self, interval_start, interval_end) -> None:
        work_entries_by_contract = defaultdict(lambda: self.env["hr.work.entry"])
        for work_entry in self:
            work_entries_by_contract[work_entry.version_id] |= work_entry

        for contract, work_entries in work_entries_by_contract.items():
            if contract.work_entry_source != "calendar":
                continue
            tz = timezone(contract._get_schedule_tz())
            resource = contract.employee_id.resource_id
            calendar_start = datetime.combine(
                max(contract.date_start, interval_start), time.min
            ).replace(tzinfo=tz)
            calendar_end = datetime.combine(
                min(contract.date_end or date.max, interval_end) + timedelta(days=1),
                time.min,
            ).replace(tzinfo=tz)
            covered_days = Intervals(
                (
                    (
                        datetime.combine(work_entry.date, time.min, tz),
                        datetime.combine(
                            work_entry.date + timedelta(days=1), time.min, tz
                        ),
                        work_entry,
                    )
                    for work_entry in work_entries
                ),
                keep_distinct=True,
            )
            outside = (
                contract.resource_calendar_id._attendance_intervals_batch(
                    calendar_start, calendar_end, resources=resource
                )[resource.id]
                - covered_days
            )
            if outside:
                time_intervals_str = "\n - ".join(
                    ["", *["%s -> %s" % (s[0], s[1]) for s in outside._items]]
                )
                employee_name = contract.employee_id.name
                msg = self.env._(
                    "Watch out for gaps in %(employee_name)s's calendar\n\nPlease complete the missing work entries of %(employee_name)s:%(time_intervals_str)s "
                    "\n\nMissing work entries are like the Bermuda Triangle for paychecks. Let's keep your colleague's earnings from vanishing into thin air!",
                    employee_name=employee_name,
                    time_intervals_str=time_intervals_str,
                )
                raise UserError(msg)

    def action_set_to_draft(self):
        return self.write({"state": "draft"})

    def action_view_payslip(self):
        self.check_singleton()
        payslips = self.env["hr.payslip"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("state", "in", ["validated", "paid"]),
                ("date_from", "<=", self.date),
                ("date_to", ">=", self.date),
                ("is_refunded", "=", False),
            ]
        )
        if not payslips:
            raise UserError(
                self.env._("No validated payslip found for this work entry.")
            )
        action = {
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
            "target": "current",
        }
        if len(payslips) == 1:
            action.update({"res_id": payslips.id, "views": [(False, "form")]})
        else:
            action.update(
                {
                    "name": self.env._("Payslips"),
                    "domain": [("id", "in", payslips.ids)],
                    "views": [(False, "list"), (False, "form")],
                }
            )
        return action

    def check_modification_allowed(self) -> None:
        for work_entry in self:
            if work_entry.state == "validated":
                raise UserError(
                    self.env._(
                        "This work entry cannot be modified because it is already associated with a generated payslip."
                    )
                )

    def write(self, vals):
        if not set(vals) - {"state", "active"}:
            return super().write(vals)
        self.check_modification_allowed()
        return super().write(vals)
