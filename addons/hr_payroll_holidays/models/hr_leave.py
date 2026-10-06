from typing import Self

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.numbers import float_compare

# How far a deferred time off may travel looking for a month that can still be
# edited. A hard bound: an employee with no contract end date would otherwise
# walk forward forever.
MAX_DEFERRAL_MONTHS = 12

LEAVE_TO_DEFER_ACTIVITY_XMLID = (
    "hr_payroll_holidays.mail_activity_data_hr_leave_to_defer"
)

_debug = DebugLog(__name__)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    payslip_state = fields.Selection(
        selection=[
            ("normal", "To compute in next payslip"),
            ("done", "Computed in current payslip"),
            ("blocked", "To defer to next payslip"),
        ],
        default="normal",
        copy=False,
        required=True,
        tracking=True,
    )

    employee_registration_number = fields.Char(
        related="employee_id.registration_number"
    )

    @api.depends("state", "employee_id", "department_id")
    def _compute_can_back_to_approve(self) -> None:
        super()._compute_can_back_to_approve()
        covered_leaves = self._leaves_covered_by_validated_payslip()
        for holiday in self:
            holiday.can_back_to_approve = (
                holiday.can_back_to_approve and holiday not in covered_leaves
            )

    @staticmethod
    def _payslip_covers_leave(payslip, leave) -> bool:
        return (
            payslip.employee_id == leave.employee_id
            and payslip.date_from <= leave._get_local_days()[1]
            and payslip.date_to >= leave._get_local_days()[0]
        )

    def _action_validate(self, check_state=True):
        # Get employees payslips, bounded to the period these leaves can
        # possibly touch. Without the two date leaves this loaded every payslip
        # the employee ever had -- 144 of them for a twelve-year history -- and
        # ran the non-stored `is_regular` compute on each, to decide about a
        # single day. `_leaves_covered_by_validated_payslip` below already
        # bounds the
        # same query this way.
        all_payslips = self._overlapping_payslips([("state", "!=", "cancel")])
        done_payslips = all_payslips.filtered(
            lambda p: p.state in ["validated", "paid"]
        )
        waiting_payslips = all_payslips - done_payslips
        # Mark Leaves to Defer
        for leave in self:
            if any(
                self._payslip_covers_leave(payslip, leave) for payslip in done_payslips
            ) and not any(
                self._payslip_covers_leave(payslip, leave)
                for payslip in waiting_payslips
            ):
                _debug.logic(
                    "leave_deferred",
                    reason="covered_by_done_payslip",
                    leave=leave,
                    done=done_payslips,
                    waiting=waiting_payslips,
                )
                leave.payslip_state = "blocked"
        res = super()._action_validate(check_state=check_state)
        self.sudo()._recompute_payslips()
        return res

    def _get_to_clean_activities(self):
        activities = super()._get_to_clean_activities()
        activities.append(LEAVE_TO_DEFER_ACTIVITY_XMLID)
        return activities

    def action_refuse(self):
        res = super().action_refuse()
        self.sudo()._recompute_payslips()
        return res

    def _move_validate_leave_to_confirm(self):
        res = super()._move_validate_leave_to_confirm()
        self.sudo()._recompute_payslips()
        self.write({"payslip_state": "normal"})
        return res

    def _action_user_cancel(self, reason=None):
        res = super()._action_user_cancel(reason)
        self.sudo().payslip_state = "done"
        self.sudo()._recompute_payslips()
        return res

    def _overlapping_payslips(self, extra_domain):
        """Regular payslips of these employees whose period can touch a leave.

        The date bounds matter: the callers narrow the result again with
        `_payslip_covers_leave`, so without them the database hands over the
        employee's whole payslip history for python to throw away.
        """
        if not self:
            return self.env["hr.payslip"]
        return (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", self.mapped("employee_id").ids),
                    ("date_from", "<=", max(self.mapped("date_to"))),
                    ("date_to", ">=", min(self.mapped("date_from"))),
                    *extra_domain,
                ]
            )
            .filtered(lambda p: p.is_regular)
        )

    def _recompute_payslips(self) -> None:
        # Recompute draft/waiting payslips
        all_payslips = self._overlapping_payslips([("state", "=", "draft")])
        draft_payslips = self.env["hr.payslip"]
        waiting_payslips = self.env["hr.payslip"]
        for leave in self:
            for payslip in all_payslips:
                if self._payslip_covers_leave(payslip, leave):
                    if not payslip.line_ids:
                        draft_payslips |= payslip
                    else:
                        waiting_payslips |= payslip
        _debug.pipeline(
            "payslips_recomputed_for_leaves",
            leaves=self,
            draft=draft_payslips,
            waiting=waiting_payslips,
        )
        if draft_payslips:
            draft_payslips._compute_worked_days_line_ids()
        if waiting_payslips:
            waiting_payslips.action_refresh_from_work_entries()

    def _cancel_work_entry_conflict(self):
        leaves_to_defer = self.filtered(lambda l: l.payslip_state == "blocked")
        _debug.pipeline("defer_activities", leaves=leaves_to_defer)
        for leave in leaves_to_defer:
            leave.activity_schedule(
                LEAVE_TO_DEFER_ACTIVITY_XMLID,
                summary=self.env._("Validated Time Off to Defer"),
                note=self.env._(
                    "Please create manually the work entry for %s",
                    leave.employee_id._get_html_link(),
                ),
                user_id=leave.employee_id.company_id.deferred_time_off_manager.id
                or self.env.ref("base.user_admin").id,
            )
        return super(HrLeave, self - leaves_to_defer)._cancel_work_entry_conflict()

    def activity_feedback(
        self,
        act_type_xmlids,
        user_id=None,
        feedback=None,
        attachment_ids=None,
        only_automated=True,
    ):
        if LEAVE_TO_DEFER_ACTIVITY_XMLID in act_type_xmlids:
            activities = self.activity_search(
                act_type_xmlids, user_id=user_id, only_automated=only_automated
            )
            self.browse(activities.mapped("res_id")).write({"payslip_state": "done"})
        return super().activity_feedback(
            act_type_xmlids,
            user_id=user_id,
            feedback=feedback,
            attachment_ids=attachment_ids,
            only_automated=only_automated,
        )

    def _get_deferral_work_entries(self):
        """Return the work entries that can still take this deferred time off.

        The month right after the time off is the usual answer, but it may be
        closed already: validating a payslip moves that month's work entries to
        'validated' and they can no longer be retyped. The time off then has to
        travel further out, and a month that far ahead may hold nothing at all
        -- the "Generate Missing Work Entries" cron only reaches the end of next
        month -- so the entries are generated on the way.
        """
        self.check_singleton()
        contract_end = self.employee_id.contract_date_end
        month = (self.date_from + relativedelta(months=1, day=1)).date()
        for _month_offset in range(MAX_DEFERRAL_MONTHS):
            if contract_end and month > contract_end:
                break
            month_end = month + relativedelta(day=31)
            work_entries = self.env["hr.work.entry"].search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    # The employee's company, not the reader's: a payroll
                    # officer looking at this from another active company
                    # matched nothing and fell into the forced regeneration
                    # below, which then created entries that same search would
                    # never see -- on every invocation.
                    ("company_id", "=", self.employee_id.company_id.id),
                    ("date", ">=", month),
                    ("date", "<=", month_end),
                ]
            )
            if not work_entries:
                # force=True: the version may already consider this range
                # generated while holding nothing for it, and without it that
                # month would be skipped for good.
                work_entries = self.employee_id.generate_work_entries(
                    month, month_end, force=True
                )
            draft_work_entries = work_entries.filtered(
                lambda entry: entry.state == "draft"
            )
            if draft_work_entries:
                return draft_work_entries.sorted("date")
            month += relativedelta(months=1)
        return self.env["hr.work.entry"]

    def action_report_to_next_month(self) -> None:
        for leave in self:
            if not leave.employee_id or leave.payslip_state != "blocked":
                raise UserError(
                    self.env._(
                        "Only an employee time off to defer can be reported to next month"
                    )
                )
            if (
                leave.date_to.year - leave.date_from.year
            ) * 12 + leave.date_to.month - leave.date_from.month > 1:
                raise UserError(
                    self.env._(
                        "The time off %s can not be reported because it is defined over more than 2 months",
                        leave.display_name,
                    )
                )
            leave_work_entries = self.env["hr.work.entry"].search(
                [
                    ("employee_id", "=", leave.employee_id.id),
                    ("company_id", "=", leave.employee_id.company_id.id),
                    ("date", ">=", leave.date_from),
                    ("date", "<=", leave.date_to),
                    # We are deferring workentry that have been reported as 'Attendance' but shouldn't have
                    ("work_entry_type_id.is_leave", "=", False),
                ]
            )
            next_month_work_entries = leave._get_deferral_work_entries()
            if not next_month_work_entries:
                raise UserError(
                    self.env._(
                        "No editable work entries were found in the %(months)s months "
                        "following time off %(leave)s, so it cannot be deferred.",
                        months=MAX_DEFERRAL_MONTHS,
                        leave=leave.display_name,
                    )
                )
            if not leave_work_entries:
                raise UserError(
                    self.env._(
                        "There is no work entries linked to this time off to report"
                    )
                )
            current_leave_hours_to_defer = leave.number_of_hours
            for work_entry in leave_work_entries:
                found = False
                for next_work_entry in next_month_work_entries:
                    if next_work_entry.work_entry_type_id.code != "WORK100":
                        continue
                    if not float_compare(
                        next_work_entry.duration, work_entry.duration, 2
                    ):
                        if (
                            float_compare(
                                next_work_entry.duration,
                                current_leave_hours_to_defer,
                                2,
                            )
                            == 1
                        ):
                            # This is required for half-day or hourly leaves.
                            # The work entry must be split according to the exact leave duration.
                            next_work_entry.action_split(
                                {
                                    "duration": current_leave_hours_to_defer,
                                    "work_entry_type_id": leave.holiday_status_id.work_entry_type_id,
                                }
                            )
                            current_leave_hours_to_defer = 0
                        else:
                            next_work_entry.work_entry_type_id = (
                                leave.holiday_status_id.work_entry_type_id
                            )
                            current_leave_hours_to_defer -= next_work_entry.duration
                        found = True
                        break
                if not found:
                    raise UserError(
                        self.env._(
                            "Not enough attendance work entries to report the time off %s. Please make the operation manually",
                            leave.display_name,
                        )
                    )
        # Should change payslip_state to 'done' at the same time
        self.activity_feedback([LEAVE_TO_DEFER_ACTIVITY_XMLID])

    def _leaves_covered_by_validated_payslip(self) -> Self:
        """The leaves of this recordset already inside a validated payslip.

        One query and one predicate, where there used to be two copies of
        both: the compute wanted the negated answer as a lookup and the guard
        wanted to raise, and each carried its own search to get there.
        """
        if not self:
            return self
        payslips = (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", self.employee_id.ids),
                    ("date_from", "<=", max(self.mapped("date_to"))),
                    ("date_to", ">=", min(self.mapped("date_from"))),
                    ("state", "in", ["validated", "paid"]),
                ]
            )
        )
        _debug.perf.count("payslip_coverage_scan", leaves=self, payslips=payslips)
        return self.filtered(
            lambda leave: any(
                self._payslip_covers_leave(p, leave) and p.is_regular for p in payslips
            )
        )

    def _check_uncovered_by_validated_payslip(self) -> None:
        if self._leaves_covered_by_validated_payslip():
            raise UserError(
                self.env._(
                    "The pay of the month is already validated with this day included. If you need to adapt, please refer to HR."
                )
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_payslip(self) -> None:
        self._check_uncovered_by_validated_payslip()
