from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.fields import Domain


class WizardHrAppraisalCreate(models.TransientModel):
    _name = "wizard.hr.appraisal.create"
    _description = "Appraisal Campaign Wizard"
    _inherit = ["mixin.hr"]

    mode = fields.Selection(
        selection=[
            ("employee", "By Employee"),
            ("company", "By Company"),
            ("department", "By Department"),
            ("category", "By Employee Tag"),
        ],
        default="employee",
        required=True,
        help="Allow to create appraisals in batches:\n- By Employee: for specific employees"
        "\n- By Company: all employees of the specified company"
        "\n- By Department: all employees of the specified department"
        "\n- By Employee Tag: all employees of the specific employee group category",
    )
    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="hr_appraisal_campaign_wizard_employee_rel",
        string="Employees",
        domain=lambda self: self._employees_domain(),
    )
    department_id = fields.Many2one(comodel_name="hr.department")
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    tag_id = fields.Many2one(
        comodel_name="res.partner.tag",
        string="Employee Tag",
    )
    manager = fields.Selection(
        selection=[
            ("employee_manager", "Employee's Manager"),
            ("person", "Other"),
        ],
        default="employee_manager",
        help="'Employee's Manager': Each appraisal will be conducted by the direct manager of the employee"
        "\n'Specific Person': All appraisals will be conducted by the specified employees",
    )
    manager_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="hr_appraisal_campaign_wizard_manager_rel",
        string="Managers",
    )
    appraisal_template_id = fields.Many2one(
        comodel_name="hr.appraisal.template",
        required=True,
        check_company=True,
    )
    appraisal_date = fields.Date(
        default=lambda self: fields.Date.today() + relativedelta(months=1),
        required=True,
    )
    warning = fields.Char(compute="_compute_warning")

    def _employees_domain(self):
        user = self.env.user
        domain = Domain([("company_id", "in", self.env.companies.ids)])
        if not user.has_group("hr_appraisal.group_hr_appraisal_user"):
            # All of the user's employee records, not the singular
            # `user.employee_id`: its compute is scoped to `env.company` alone,
            # while the company half of this domain widens to `env.companies`,
            # so the two disagreed by construction and a user holding an
            # employee in a second company silently lost every report under it.
            # Every internal user reaches this branch — `base.group_user` has
            # create on the wizard and both "Launch Campaign" buttons carry
            # that group.
            domain &= Domain([("id", "child_of", user.employee_ids.ids)])
        return domain

    @api.depends(
        "mode",
        "manager",
        "manager_ids",
        "employee_ids",
        "company_id",
        "department_id",
        "tag_id",
        "appraisal_date",
    )
    def _compute_warning(self) -> None:
        for wizard in self:
            wizard.warning = "\n".join(
                "- " + warning for warning in wizard._get_warnings()
            )

    def _get_warnings(self):
        """The warnings `warning` renders, one wizard at a time."""
        self.check_singleton()
        warnings = []
        employees = self._get_employees_from_mode()

        if not employees:
            if self.mode == "company" and self.company_id:
                warnings.append(
                    self.env._(
                        "The company %(company_name)s doesn't have employees",
                        company_name=self.company_id.name,
                    )
                )

            elif self.mode == "department" and self.department_id:
                warnings.append(
                    self.env._(
                        "The department %(department_name)s doesn't have employees",
                        department_name=self.department_id.name,
                    )
                )

            elif self.mode == "category" and self.tag_id:
                warnings.append(
                    self.env._(
                        "No employees have the tag %(category_name)s",
                        category_name=self.tag_id.name,
                    )
                )

        if self.manager == "employee_manager":
            employees_without_managers = employees.filtered(
                lambda emp: not emp.parent_id or emp.parent_id == emp._origin
            )
            if employees_without_managers:
                warnings.append(
                    self.env._(
                        "Appraisals won't be created for the following employees because they don't have a manager: %(employees)s",
                        employees=", ".join(employees_without_managers.mapped("name")),
                    )
                )

        similar_appraisals = self._get_appraisals_with_same_date_and_managers(employees)
        if similar_appraisals:
            warnings.append(
                self.env._(
                    "The following employees already have appraisals on %(appraisal_date)s: %(employees)s. The existing appraisals will be used instead of creating new ones.",
                    appraisal_date=self.appraisal_date,
                    employees=", ".join(similar_appraisals.mapped("employee_id.name")),
                )
            )
        return warnings

    def _get_expected_managers(self, employee):
        """The managers this campaign would give `employee`."""
        if self.manager == "person":
            return self.manager_ids.filtered(lambda m: m.id != employee.id)
        return employee.parent_id if employee.parent_id != employee else False

    def _get_appraisals_with_same_date_and_managers(self, employees):
        # One query for the whole campaign instead of one per employee, and one
        # call per action instead of two: `_compute_warning` and
        # `_create_employees_appraisals` both need this set.
        candidates = (
            self.env["hr.appraisal"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", employees.ids),
                    ("date_close", "=", self.appraisal_date),
                ]
            )
        )
        similar_ids = []
        for appraisal in candidates:
            managers = self._get_expected_managers(appraisal.employee_id)
            if managers and set(managers.ids).issubset(appraisal.manager_ids.ids):
                similar_ids.append(appraisal.id)
        return self.env["hr.appraisal"].browse(similar_ids)

    def action_generate_appraisals(self):
        employees = self._get_employees_from_mode()
        appraisals = self._create_employees_appraisals(employees)
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "hr_appraisal.hr_appraisal_action_multiple_appraisals"
        )
        action["domain"] = [("id", "in", appraisals.ids)]
        action["context"] = self.env.context
        return action

    def _get_employees_from_mode(self):
        if self.mode == "employee":
            # No implicit "everyone": an empty selection used to expand to every
            # employee in every allowed company and launch a company-wide
            # campaign by accident.
            employees = self.employee_ids
        elif self.mode == "company":
            employees = self.env["hr.employee"].search(
                [("company_id", "=", self.company_id.id)]
            )
        elif self.mode == "category":
            employees = self.tag_id.employee_ids.filtered(
                lambda e: e.company_id in self.env.companies
            )
        else:
            employees = self.department_id.member_ids
        # The access domain can no longer carry this: scope the result to the
        # employees this user is allowed to launch a campaign for, which is what
        # `_employees_domain` already describes for the employee_ids widget.
        return employees.filtered_domain(self._employees_domain())

    def _create_employees_appraisals(self, employees):
        similar_appraisals = self._get_appraisals_with_same_date_and_managers(employees)
        employees_without_appraisal = employees - similar_appraisals.employee_id
        create_vals = []
        for employee in employees_without_appraisal:
            managers = self._get_expected_managers(employee)
            # A warning will be generated in compute_warning about employees without a direct manager.
            if managers:
                create_vals.append(
                    {
                        "employee_id": employee.id,
                        "manager_ids": managers,
                        "date_close": self.appraisal_date,
                        "appraisal_template_id": self.appraisal_template_id.id,
                        "state": "2_pending",
                        "employee_feedback_published": False,
                        "manager_feedback_published": False,
                    }
                )

        return similar_appraisals + self.env["hr.appraisal"].create(create_vals)
