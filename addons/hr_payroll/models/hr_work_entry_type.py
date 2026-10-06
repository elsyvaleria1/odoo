from odoo import api, fields, models
from odoo.exceptions import UserError


class HrWorkEntryType(models.Model):
    _inherit = "hr.work.entry.type"
    _description = "HR Work Entry Type"

    _is_unforeseen_is_leave = models.Constraint(
        "check (is_unforeseen IS NOT TRUE OR (is_leave = TRUE and is_unforeseen = TRUE))",
        "A unforeseen absence must be a leave.",
    )

    is_unforeseen = fields.Boolean(
        string="Unforeseen Absence",
        default=False,
        help="The Work Entry checked as Unforeseen Absence will be counted in absenteeism at work report.",
    )
    round_days = fields.Selection(
        selection=[("NO", "No Rounding"), ("HALF", "Half Day"), ("FULL", "Day")],
        string="Rounding",
        default="NO",
        required=True,
        help="When the work entry is displayed in the payslip, the value is rounded accordingly.",
    )
    round_days_type = fields.Selection(
        selection=[("HALF-UP", "Closest"), ("UP", "Up"), ("DOWN", "Down")],
        string="Round Type",
        default="DOWN",
        required=True,
        help="Way of rounding the work entry type.",
    )
    unpaid_structure_ids = fields.Many2many(
        comodel_name="hr.payroll.structure",
        relation="hr_payroll_structure_hr_work_entry_type_rel",
        string="Unpaid in Structures Types",
        help="The work entry won’t grant any money to employee in payslip.",
    )
    current_companies_country_codes = fields.Char(
        string="country codes",
        compute="_compute_current_companies_country_codes",
    )

    @api.depends_context("allowed_company_ids")
    def _compute_current_companies_country_codes(self) -> None:
        self.current_companies_country_codes = ",".join(
            self.env.companies.mapped("country_id.code")
        )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_work_entry_type(self) -> None:
        if self:
            raise UserError(
                self.env._("You cannot delete work entry type(s). Instead archive it.")
            )
