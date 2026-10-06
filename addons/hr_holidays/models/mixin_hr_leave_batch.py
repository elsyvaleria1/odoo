from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.fields import Domain

if TYPE_CHECKING:
    from odoo.addons.hr.models.hr_employee import HrEmployee


class MixinHrLeaveBatch(models.AbstractModel):
    _name = "mixin.hr.leave.batch"
    _inherit = ["mixin.hr"]
    _description = "Employee Selection for Batch Time Off"

    def _domain_employee_ids(self) -> Domain:
        domain = Domain([("company_id", "in", self.env.companies.ids)])
        if not self.env.user.has_group("hr_holidays.group_hr_holidays_user"):
            domain &= Domain(
                [
                    "|",
                    ("leave_manager_id", "=", self.env.user.id),
                    ("user_id", "=", self.env.user.id),
                ]
            )
        return domain

    allocation_mode = fields.Selection(
        selection=[
            ("employee", "By Employee"),
            ("company", "By Company"),
            ("department", "By Department"),
            ("category", "By Employee Tag"),
        ],
        default="employee",
        readonly=False,
        required=True,
        help="Allow to create requests in batchs:\n- By Employee: for a specific employee"
        "\n- By Company: all employees of the specified company"
        "\n- By Department: all employees of the specified department"
        "\n- By Employee Tag: all employees of the specific employee group category",
    )

    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Employees",
        domain=lambda self: self._domain_employee_ids(),
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    department_id = fields.Many2one(comodel_name="hr.department")

    tag_id = fields.Many2one(
        comodel_name="res.partner.tag",
        string="Employee Tag",
    )

    def _get_employees_from_allocation_mode(self) -> HrEmployee:
        self.check_singleton()
        if self.allocation_mode == "employee":
            employees = self.employee_ids or self.env["hr.employee"].search(
                self._domain_employee_ids()
            )
        elif self.allocation_mode == "category":
            employees = self.tag_id.employee_ids.filtered(
                lambda e: e.company_id in self.env.companies
            )
        elif self.allocation_mode == "company":
            employees = self.env["hr.employee"].search(
                [("company_id", "=", self.company_id.id)]
            )
        else:
            employees = self.department_id.member_ids
        return employees
