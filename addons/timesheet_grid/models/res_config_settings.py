from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    reminder_user_allow = fields.Boolean(
        related="company_id.timesheet_mail_employee_allow",
        string="Employee Reminder",
        readonly=False,
    )
    reminder_user_delay = fields.Integer(
        related="company_id.timesheet_mail_employee_delay",
        string="Days to Remind User",
        readonly=False,
        help="Numbers of days after the end of the week/month after which an automatic email reminder will be sent to timesheet users that still have timesheets to encode (according to their working hours).",
    )
    reminder_user_interval = fields.Selection(
        related="company_id.timesheet_mail_employee_interval",
        string="User Reminder Frequency",
        readonly=False,
        required=True,
    )

    reminder_allow = fields.Boolean(
        related="company_id.timesheet_mail_allow",
        string="Approver Reminder",
        readonly=False,
    )
    reminder_delay = fields.Integer(
        related="company_id.timesheet_mail_delay",
        string="Days to Remind Approver",
        readonly=False,
        help="Number of days after the end of the week/month after which an automatic email reminder will be sent to timesheet managers that still have timesheets to validate.",
    )
    reminder_interval = fields.Selection(
        related="company_id.timesheet_mail_interval",
        string="Approver Reminder Frequency",
        readonly=False,
        required=True,
    )
    timesheet_min_duration = fields.Integer(
        string="Minimal Duration",
        default=15,
        config_parameter="timesheet_grid.timesheet_min_duration",
    )
    timesheet_rounding = fields.Integer(
        string="Round up",
        default=15,
        config_parameter="timesheet_grid.timesheet_rounding",
    )
