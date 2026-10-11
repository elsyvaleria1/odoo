from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import frozendict


class ResourceScheduleException(models.Model):
    _inherit = "resource.schedule.exception"
    _access_anchors = frozendict(
        {
            "owner": "resource_id.user_id",
            "owner_or_unset": models.Anchor(
                "resource_id.user_id", kind="owner", shared=True
            ),
        }
    )

    holiday_id = fields.Many2one(
        comodel_name="hr.leave",
        string="Time Off Request",
    )
    eligible_for_accrual_rate = fields.Boolean(
        string="Eligible for Accrual Rate",
        default=False,
        help="If checked, this time off type will be taken into account for accruals computation.",
    )

    @api.model
    def _get_domain_projection(self, record):
        if record._name == "hr.leave":
            return Domain("holiday_id", "=", record.id)
        return super()._get_domain_projection(record)

    @api.model
    def _prepare_projection_link_vals(self, record):
        if record._name == "hr.leave":
            return {"holiday_id": record.id}
        return super()._prepare_projection_link_vals(record)

    @api.constrains("date_from", "date_to", "calendar_id")
    def _check_compare_dates(self) -> None:
        dated = self.filtered(lambda leave: leave.date_from and leave.date_to)
        if not dated:
            return
        all_existing_leaves = self.search(
            self._get_domain_public_holidays(
                min(dated.mapped("date_from")),
                max(dated.mapped("date_to")),
                companies=dated.company_id,
            )
        )
        for record in dated:
            if not record.resource_id:
                existing_leaves = (all_existing_leaves - record).filtered_domain(
                    [
                        ("company_id", "=", record.company_id.id),
                        ("date_to", ">", record.date_from),
                        ("date_from", "<", record.date_to),
                    ]
                )
                if record.calendar_id:
                    existing_leaves = existing_leaves.filtered_domain(
                        [("calendar_id", "in", [False, record.calendar_id.id])]
                    )
                if existing_leaves:
                    raise ValidationError(
                        self.env._(
                            "Two public holidays cannot overlap each other for the same working hours."
                        )
                    )

    def _get_domain_for_periods(self, time_domain_dict):
        return Domain.OR(
            [
                ("employee_company_id", "=", date["company_id"]),
                ("date_to", ">", date["date_from"]),
                ("date_from", "<", date["date_to"]),
            ]
            for date in time_domain_dict
        ) & Domain("state", "not in", ["refuse", "cancel"])

    def _reevaluate_leaves(self, time_domain_dict) -> None:
        if not time_domain_dict:
            return
        time_domain_dict = list(
            {tuple(sorted(entry.items())): entry for entry in time_domain_dict}.values()
        )

        domain = self._get_domain_for_periods(time_domain_dict)
        leaves = self.env["hr.leave"].search(domain)
        if not leaves:
            return

        previous_durations = leaves.mapped("number_of_days")
        previous_states = leaves.mapped("state")
        self.env.add_to_compute(self.env["hr.leave"]._fields["number_of_days"], leaves)
        leaves.modified(["number_of_days"])
        leaves.sudo().write(
            {
                "state": "confirm",
            }
        )
        sick_time_status = self.env.ref(
            "hr_holidays.leave_type_sick_time_off", raise_if_not_found=False
        )
        leaves_to_recreate = self.env["hr.leave"]
        for previous_duration, leave, state in zip(
            previous_durations, leaves, previous_states, strict=False
        ):
            duration_difference = previous_duration - leave.number_of_days
            message = False
            if duration_difference > 0 and leave.holiday_status_id.requires_allocation:
                message = self.env._(
                    "Due to a change in global time offs, you have been granted %s day(s) back.",
                    duration_difference,
                )
            if leave.number_of_days > previous_duration and (
                not sick_time_status or leave.holiday_status_id not in sick_time_status
            ):
                message = self.env._(
                    "Due to a change in global time offs, %s extra day(s) have been taken from your allocation. Please review this leave if you need it to be changed.",
                    -1 * duration_difference,
                )
            try:
                leave.sudo().write({"state": state})
                leave._check_validity()
                if leave.state == "validate":
                    leaves_to_recreate |= leave
            except ValidationError:
                leave.action_refuse()
                message = self.env._(
                    "Due to a change in global time offs, this leave no longer has the required amount of available allocation and has been set to refused. Please review this leave."
                )
            if message:
                leave._notify_change(message)
        leaves_to_recreate.sudo()._create_resource_leave()

    @api.model
    def _on_schedule_changed(self, scopes) -> None:
        super()._on_schedule_changed(scopes)
        self._reevaluate_leaves(
            [
                {
                    "company_id": scope["company_id"],
                    "date_from": scope["date_from"],
                    "date_to": scope["date_to"],
                }
                for scope in scopes
                if not scope["resource_id"]
            ]
        )

    def load_public_holidays(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Load Public Holidays"),
            "res_model": "wizard.resource.schedule.exception.load.public.holiday",
            "view_mode": "form",
            "target": "new",
        }

    @api.depends("holiday_id.employee_id.company_id")
    def _compute_company_id(self):
        super()._compute_company_id()
        for leave in self:
            if leave.holiday_id.employee_id.company_id:
                leave.company_id = leave.holiday_id.employee_id.company_id

    def _get_flexible_windows(self, calendar, tz) -> list[tuple]:
        holiday = self.holiday_id
        if holiday.request_unit_half or holiday.request_unit_hours:
            return holiday._daily_windows(tz)
        return super()._get_flexible_windows(calendar, tz)


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    associated_leaves_count = fields.Integer(
        string="Time Off Count",
        compute="_compute_associated_leaves_count",
    )

    def _handle_flexible_leave_interval(self, dt0, dt1, leave):
        holiday = leave.sudo().holiday_id
        if holiday.request_unit_half or holiday.request_unit_hours:
            return dt0, dt1
        return super()._handle_flexible_leave_interval(dt0, dt1, leave)

    def _compute_associated_leaves_count(self) -> None:
        leaves_read_group = self.env["resource.schedule.exception"]._read_group(
            self.env["resource.schedule.exception"]._get_domain_public_holidays(
                calendars=self
            ),
            ["calendar_id"],
            ["__count"],
        )
        result = {
            calendar.id if calendar else "global": count
            for calendar, count in leaves_read_group
        }
        global_leave_count = result.get("global", 0)
        for calendar in self:
            calendar.associated_leaves_count = (
                result.get(calendar.id, 0) + global_leave_count
            )


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    leave_date_to = fields.Date(related="user_id.leave_date_to")

    def _sync_state_from_leaves(self) -> None:
        people = self.filtered(lambda resource: resource.type == "human")
        if not people:
            return
        now = fields.Datetime.now()
        on_leave = (
            self.env["hr.leave"]
            .search(
                [
                    ("employee_id.resource_id", "in", people.ids),
                    ("state", "=", "validate"),
                    ("date_from", "<=", now),
                    ("date_to", ">", now),
                ]
            )
            .employee_id.resource_id
        )
        (people & on_leave).filtered(
            lambda resource: resource.state in ("available", "in_service")
        )._transition("maintenance")
        (people - on_leave).filtered(
            lambda resource: resource.state == "maintenance"
        )._end_maintenance()

    @api.model
    def _cron_sync_state_from_leaves(self) -> None:
        cron = self.env.ref(
            "hr_holidays.ir_cron_resource_state_from_leaves", raise_if_not_found=False
        )
        now = fields.Datetime.now()
        since = (cron and cron.lastcall) or now - timedelta(days=1)
        self.env["hr.leave"].with_privilege(
            "hr_holidays.privilege_follow_leave_state",
            reason="time off moves a person on leave and back",
        ).search(
            [("state", "=", "validate")]
            + Domain.OR(
                [
                    [("date_from", ">", since), ("date_from", "<=", now)],
                    [("date_to", ">", since), ("date_to", "<=", now)],
                ]
            )
        ).employee_id.resource_id._sync_state_from_leaves()
