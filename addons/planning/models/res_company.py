from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    planning_generation_interval = fields.Integer(
        string="Rate Of Shift Generation",
        default=6,
        readonly=False,
        required=True,
    )

    planning_employee_unavailabilities = fields.Selection(
        selection=[
            ("switch", "Switch shifts with other employees"),
            ("unassign", "Unassign themselves from shifts"),
        ],
        string="Employee Unavailabilities",
        default="switch",
        required=True,
    )

    planning_self_unassign_days_before = fields.Integer(
        string="Days before shift for unassignment",
        help="Deadline in days for shift unassignment",
    )

    _planning_self_unassign_days_before_positive = models.Constraint(
        "CHECK(planning_self_unassign_days_before >= 0)",
        "The amount of days before unassignment must be positive or equal to zero.",
    )
