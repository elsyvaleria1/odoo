from odoo import api, fields, models


class HrPayslipLine(models.Model):
    _inherit = "hr.payslip.line"

    debit_tag_ids = fields.Many2many(
        comodel_name="account.account.tag",
        string="Debit Tax Grids",
        compute="_compute_debit_tags",
        help="Tags assigned to this line will impact financial reports when translated into an accounting journal entry."
        "They will be applied on the debit account line in the journal entry.",
    )
    credit_tag_ids = fields.Many2many(
        comodel_name="account.account.tag",
        string="Credit Tax Grids",
        compute="_compute_credit_tags",
        help="Tags assigned to this line will impact financial reports when translated into an accounting journal entry."
        "They will be applied on the credit account line in the journal entry.",
    )

    salary_rule_account_debit = fields.Many2one(
        comodel_name="account.account",
        string="Debit Account",
        compute="_compute_salary_rule_accounts",
        groups="account.group_account_readonly",
    )
    salary_rule_account_credit = fields.Many2one(
        comodel_name="account.account",
        string="Credit Account",
        compute="_compute_salary_rule_accounts",
        groups="account.group_account_readonly",
    )

    @api.depends("salary_rule_id", "company_id")
    def _compute_salary_rule_accounts(self) -> None:
        # `account_debit` and `account_credit` are company_dependent on the rule,
        # so reading them off it with a plain `related=` would answer in whatever
        # company the user happens to be in rather than in the one the payslip
        # belongs to.
        for line in self:
            rule = line.salary_rule_id.with_company(line.company_id or self.env.company)
            line.salary_rule_account_debit = rule.account_debit
            line.salary_rule_account_credit = rule.account_credit

    @api.depends("salary_rule_id")
    def _compute_debit_tags(self) -> None:
        # To be overridden for specific localisation cases
        for record in self:
            record.debit_tag_ids = record.salary_rule_id.debit_tag_ids.ids

    @api.depends("salary_rule_id")
    def _compute_credit_tags(self) -> None:
        # To be overridden for specific localisation cases
        for record in self:
            record.credit_tag_ids = record.salary_rule_id.credit_tag_ids.ids
