from datetime import date

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"
    _description = "Employee"

    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        string="Currency",
    )
    slip_ids = fields.One2many(
        comodel_name="hr.payslip",
        inverse_name="employee_id",
        string="Payslips",
        readonly=True,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    payslip_count = fields.Count(
        count_of="slip_ids",
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    registration_number = fields.Char(
        string="Employee Reference",
        copy=False,
        tracking=True,
        classification="hr.private",
    )
    salary_attachment_ids = fields.Many2many(
        comodel_name="hr.salary.attachment",
        string="Salary Adjustments",
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    salary_attachment_count = fields.Count(
        count_of="salary_attachment_ids",
        string="Salary Adjustment Count",
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    mobile_invoice = fields.Binary(
        string="Mobile Subscription Invoice",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    sim_card = fields.Binary(
        string="SIM Card Copy",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    internet_invoice = fields.Binary(
        string="Internet Subscription Invoice",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    structure_type_id = fields.Many2one(
        related="version_id.structure_type_id",
        inherited=True,
        readonly=False,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    contract_type_id = fields.Many2one(
        related="version_id.contract_type_id",
        inherited=True,
        readonly=False,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    monthly_running_attachments = fields.Monetary(
        compute="_compute_monthly_running_attachments",
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )

    _unique_registration_number = models.Constraint(
        "UNIQUE(registration_number, company_id)",
        "No duplication of registration numbers is allowed",
    )

    def _compute_monthly_running_attachments(self) -> None:
        for employee in self:
            running_attachment_ids = employee.salary_attachment_ids.filtered(
                lambda a: a.state == "open"
            )
            employee.monthly_running_attachments = sum(
                running_attachment_ids.mapped("monthly_amount")
            )

    def action_view_payslips(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_payroll.action_view_hr_payslip_month_form"
        )
        action.update(
            {
                "domain": [("employee_id", "=", self.id)],
                "context": {
                    "search_default_group_by_version_id": 1,
                    "default_employee_id": self.id,
                },
            }
        )
        return action

    def action_view_salary_attachments(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_payroll.hr_salary_attachment_action"
        )
        action.update(
            {
                "domain": [("employee_ids", "in", self.ids)],
                "context": {"default_employee_ids": self.ids},
            }
        )
        return action

    def _index_employee_contracts(self, multi_employees=False):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_payroll.action_hr_payroll_index"
        )
        if not multi_employees:
            self.check_singleton()
            action["context"] = {
                "default_version_ids": self.version_id.ids,
                "active_employee_id": self.id,
            }
        else:
            action["context"] = {"default_employee_ids": self.ids}
        return action

    @api.model
    def _get_account_holder_employees_data(self):
        # as acc_type isn't stored we can not use a domain to retrieve the employees
        # bypass orm for performance, we only care about the employee id anyway

        # return nothing if user has no right to either employee or bank partner
        if not self.browse().has_access("read") or not self.env[
            "res.partner.bank.account"
        ].has_access("read"):
            return []

        self.env.cr.execute(
            """
            SELECT emp.id,
                   acc.acc_number,
                   acc.allow_out_payment
              FROM hr_employee emp
         LEFT JOIN hr_employee_bank_allocation alloc
                ON alloc.employee_id=emp.id
         LEFT JOIN res_partner_bank_account acc
                ON acc.id=alloc.bank_account_id
             WHERE emp.company_id = ANY(%s)
               AND emp.active = TRUE
        """,
            (list(self.env.companies.ids),),
        )

        return self.env.cr.dictfetchall()

    @api.model
    def _get_untrusted_bank_account_ids(self) -> list:
        """Return a list of bank account IDs linked to employees that are not marked for out payment."""
        if not self.browse().has_access("read") or not self.env[
            "res.partner.bank.account"
        ].has_access("read"):
            return []

        self.env.cr.execute(
            """
            SELECT acc.id
            FROM res_partner_bank_account acc
            JOIN hr_employee_bank_allocation alloc
                ON alloc.bank_account_id = acc.id
            JOIN hr_employee emp
                ON emp.id = alloc.employee_id
            WHERE acc.allow_out_payment = FALSE
            AND emp.company_id = ANY(%s)
            AND emp.active = TRUE
        """,
            (list(self.env.companies.ids),),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def action_configure_employee_inputs(self):
        self.check_singleton()
        action = self.structure_id.action_get_structure_inputs()
        action["domain"].append(("input_usage_employee", "=", True))
        return action

    def _get_employee_fields_that_recompute_payslip(self):
        return []

    def write(self, vals):
        res = super().write(vals)
        if vals.keys() & set(self._get_employee_fields_that_recompute_payslip()):
            for version in self.sudo().version_ids:
                version._recompute_payslips(
                    version.date_start, version.date_end or date.max
                )
        return res
