from odoo import api, fields, models
from odoo.exceptions import UserError


class HrPayrollStructureType(models.Model):
    _inherit = "hr.payroll.structure.type"
    _description = "Salary Structure Type"
    _order = "sequence, id"

    def _get_selection_schedule_pay(self) -> list:
        return [
            ("annually", "year"),
            ("semi-annually", "half-year"),
            ("quarterly", "quarter"),
            ("bi-monthly", "2 months"),
            ("monthly", "month"),
            ("semi-monthly", "half-month"),
            ("bi-weekly", "2 weeks"),
            ("weekly", "week"),
            ("daily", "day"),
        ]

    sequence = fields.Integer(default=10)
    name = fields.Char(
        string="Structure Type",
        required=True,
    )
    default_schedule_pay = fields.Selection(
        selection=lambda self: self._get_selection_schedule_pay(),
        string="Scheduled Pay",
        default="monthly",
        help="Defines the frequency of the wage payment.",
    )
    struct_ids = fields.One2many(
        comodel_name="hr.payroll.structure",
        inverse_name="type_id",
        string="Structures",
    )
    default_struct_id = fields.Many2one(
        comodel_name="hr.payroll.structure",
        string="Pay Structure",
    )
    default_work_entry_type_id = fields.Many2one(
        comodel_name="hr.work.entry.type",
        string="Work Entry Type",
        default=lambda self: self.env.ref(
            "hr_work_entry.work_entry_type_attendance", raise_if_not_found=False
        ),
        required=True,
        help="Work entry type for regular attendances.",
    )
    wage_type = fields.Selection(
        selection=[("monthly", "Fixed Wage"), ("hourly", "Hourly Wage")],
        default="monthly",
        required=True,
    )
    struct_type_count = fields.Count(
        count_of="struct_ids",
        string="Structure Type Count",
    )

    @api.constrains("country_id")
    def _check_country(self) -> None:
        if self.env.context.get("install_mode"):
            return
        for structure_type in self:
            if (
                structure_type.country_id
                and structure_type.country_id.id
                not in self.env.companies.mapped("country_id").ids
            ):
                raise UserError(
                    self.env._(
                        "You should also be logged into a company in %s to set this country.",
                        structure_type.country_id.name,
                    )
                )
