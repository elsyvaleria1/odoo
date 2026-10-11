from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HelpdeskTicket(models.Model):
    _name = "helpdesk.ticket"
    _inherit = ["helpdesk.ticket", "mixin.timer.parent"]

    def _default_team_id(self):
        if project_id := self.env.context.get("default_project_id"):
            if (
                team_id := self.env["team.team"]
                .search([("project_id", "=", project_id)], limit=1)
                .id
            ):
                return team_id

        return super()._default_team_id()

    team_id = fields.Many2one(
        domain="[('use_helpdesk', '=', True), ('use_helpdesk_timesheet', '=', True)] if context.get('default_project_id') else [('use_helpdesk', '=', True)]"
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        related="team_id.project_id",
        store=True,
        index="btree_not_null",
        readonly=True,
    )
    timesheet_ids = fields.One2many(
        comodel_name="account.analytic.line",
        inverse_name="helpdesk_ticket_id",
        string="Timesheets",
        help="Time spent on this ticket. By default, your timesheets will be linked to the sales order item of your ticket.\n"
        "Remove the sales order item to make your timesheet entries non billable.",
    )
    use_helpdesk_timesheet = fields.Boolean(
        related="team_id.use_helpdesk_timesheet",
        string="Timesheet activated on Team",
        readonly=True,
    )
    display_timesheet_timer = fields.Boolean(
        string="Display Timesheet Time",
        compute="_compute_display_timesheet_timer",
    )
    timesheet_unit_amount = fields.Float(compute="_compute_timesheet_unit_amount")
    total_hours_spent = fields.Float(
        string="Time Spent",
        compute="_compute_total_hours_spent",
        compute_sudo=True,
        default=0,
        store=True,
        aggregator="avg",
    )
    encode_uom_in_days = fields.Boolean(
        export_string_translation=False,
        compute="_compute_encode_uom_in_days",
    )
    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        compute="_compute_analytic_account_id",
        store=True,
        readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )

    def _compute_encode_uom_in_days(self) -> None:
        self.encode_uom_in_days = (
            self.env.company.hr_timesheet_config_id.timesheet_encode_uom_id
            == self.env.ref("base.product_uom_day")
        )

    @api.depends("use_helpdesk_timesheet", "timesheet_ids", "encode_uom_in_days")
    def _compute_display_timesheet_timer(self) -> None:
        _debug.pipeline("ticket_timer_visibility", tickets=self)
        for ticket in self:
            ticket.display_timesheet_timer = (
                ticket.use_helpdesk_timesheet and not ticket.encode_uom_in_days
            )

    @api.depends("user_timer_id")
    def _compute_timesheet_unit_amount(self) -> None:
        if not any(self._ids):
            for ticket in self:
                unit_amount = 0.0
                if (
                    ticket.user_timer_id
                    and (ticket.id or ticket.origin.id) == ticket.user_timer_id.id
                ):
                    unit_amount = ticket.unit_amount or 0.0
                ticket.timesheet_unit_amount = unit_amount
            return
        timesheet_id_per_timer_id = {
            ticket.user_timer_id.id: ticket.user_timer_id.res_id for ticket in self
        }
        timesheet_read = self.env["account.analytic.line"].search_read(
            [("id", "in", list(timesheet_id_per_timer_id.values()))],
            ["unit_amount"],
        )
        unit_amount_per_timesheet_id = {
            res["id"]: res["unit_amount"] for res in timesheet_read
        }
        for ticket in self:
            timesheet_id = timesheet_id_per_timer_id.get(ticket.user_timer_id.id, False)
            _debug.logic(
                "ticket_timer_unit_amount",
                ticket=ticket,
                timer=ticket.user_timer_id,
                timesheet=timesheet_id,
                found=timesheet_id in unit_amount_per_timesheet_id,
            )
            if timesheet_id:
                ticket.timesheet_unit_amount = unit_amount_per_timesheet_id.get(
                    timesheet_id, 0.0
                )
            else:
                ticket.timesheet_unit_amount = 0.0

    @api.depends("timesheet_ids.unit_amount")
    def _compute_total_hours_spent(self) -> None:
        if not any(self._ids):
            for ticket in self:
                ticket.total_hours_spent = sum(
                    ticket.timesheet_ids.mapped("unit_amount")
                )
            return
        _debug.pipeline(
            "ticket_total_hours_from_read_group",
            tickets=self,
            by="read_group",
        )
        timesheet_read_group = self.env["account.analytic.line"]._read_group(
            [("helpdesk_ticket_id", "in", self.ids)],
            ["helpdesk_ticket_id"],
            ["unit_amount:sum"],
        )
        timesheets_per_ticket = {
            helpdesk_ticket.id: unit_amount_sum
            for helpdesk_ticket, unit_amount_sum in timesheet_read_group
        }
        for ticket in self:
            ticket.total_hours_spent = timesheets_per_ticket.get(ticket.id, 0.0)

    @api.onchange("team_id")
    def _onchange_team_id(self) -> dict | None:
        if (
            self.timesheet_ids
            and not self.team_id.use_helpdesk_timesheet
            and not all(t.validated for t in self.timesheet_ids)
        ):
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "Moving this task to a helpdesk team without timesheet support will retain timesheet drafts in the original helpdesk team. "
                        "Although they won't be visible here, you can still edit them using the Timesheets app."
                    ),
                    "type": "notification",
                },
            }
        return None

    @api.model_create_multi
    def create(self, vals_list):
        default_project_id = self.env.context.get("default_project_id")
        for vals in vals_list:
            project_id = vals.get("project_id") or default_project_id
            if not vals.get("team_id") and project_id:
                project = self.env["project.project"].browse(project_id)
                if project.helpdesk_team:
                    _debug.logic(
                        "ticket_team_from_project",
                        project=project,
                        teams=project.helpdesk_team,
                        chosen=project.helpdesk_team[0],
                    )
                    vals["team_id"] = project.helpdesk_team[0].id
        return super().create(vals_list)

    @api.depends("project_id")
    def _compute_analytic_account_id(self) -> None:
        for ticket in self:
            ticket.analytic_account_id = ticket.project_id.account_id

    @api.depends("use_helpdesk_timesheet")
    def _compute_display_extra_info(self) -> None:
        if self.env.user.has_group("analytic.group_analytic_accounting"):
            show_analytic_account_id_records = self.filtered("use_helpdesk_timesheet")
            show_analytic_account_id_records.display_extra_info = True
            super(
                HelpdeskTicket, self - show_analytic_account_id_records
            )._compute_display_extra_info()
        else:
            super()._compute_display_extra_info()

    def write(self, vals):
        res = super().write(vals)
        if vals.get("team_id"):
            if not self.team_id.use_helpdesk_timesheet:
                timers = self.env["timer.timer"].search(
                    [
                        ("parent_res_model", "=", "helpdesk.ticket"),
                        ("parent_res_id", "in", self.ids),
                        ("res_model", "=", "account.analytic.line"),
                    ]
                )
                if timers:
                    timesheets = (
                        self.env["account.analytic.line"]
                        .browse(timers.mapped("res_id"))
                        .sudo()
                    )
                    timers.unlink()
                    if timesheets_to_remove := timesheets.filtered(
                        lambda t: t.unit_amount == 0
                    ):
                        timesheets_to_remove.unlink()
            timesheet_read_group = self.env["account.analytic.line"]._read_group(
                [
                    ("project_id", "!=", False),
                    ("helpdesk_ticket_id", "in", self.ids),
                    ("validated", "=", False),
                ],
                ["helpdesk_ticket_id"],
                ["id:recordset"],
            )
            for ticket, timesheets in timesheet_read_group:
                if ticket.use_helpdesk_timesheet and ticket.project_id:
                    timesheets_to_update = timesheets.filtered_domain(
                        [("project_id", "!=", ticket.project_id.id)]
                    )
                    timesheets_to_update.project_id = ticket.project_id
                else:
                    timesheets.helpdesk_ticket_id = False
        return res

    def action_timer_start(self):
        if self.display_timesheet_timer:
            super().action_timer_start()

    def action_timer_stop(self):
        if self.display_timesheet_timer and self.user_timer_id:
            timesheet = self._get_record_with_timer_running()
            if timesheet:
                return {
                    "name": self.env._("Confirm Time Spent"),
                    "type": "ir.actions.act_window",
                    "res_model": "hr.timesheet.stop.timer.confirmation.wizard",
                    "context": {
                        "default_timesheet_id": timesheet.id,
                        "dialog_size": "medium",
                    },
                    "views": [
                        [
                            self.env.ref(
                                "timesheet_grid.hr_timesheet_stop_timer_confirmation_wizard_view_form"
                            ).id,
                            "form",
                        ]
                    ],
                    "target": "new",
                }
            else:
                return super().action_timer_stop()
        return False

    def _create_record_to_start_timer(self):
        return self.env["account.analytic.line"].create(
            {
                "helpdesk_ticket_id": self.id,
                "project_id": self.project_id.id,
                "date": fields.Date.context_today(self),
                "name": "/",
                "user_id": self.env.uid,
            }
        )

    def _action_interrupt_user_timers(self) -> None:
        self.action_timer_stop()
