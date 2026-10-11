from odoo import fields, models
from odoo.exceptions import RedirectWarning, UserError


class HrExpense(models.Model):
    _inherit = "hr.expense"

    refund_in_payslip = fields.Boolean(string="Reimburse In Next Payslip")
    payslip_id = fields.Many2one(
        comodel_name="hr.payslip",
        index="btree_not_null",
        readonly=True,
    )

    def _compute_is_editable(self) -> None:
        super()._compute_is_editable()
        for expense in self:
            expense.is_editable = expense.is_editable and not expense.payslip_id

    def _get_countries_allowing_payslips(self) -> set:
        return {
            country_sudo.id if country_sudo else False
            for (country_sudo,) in self.env["hr.payroll.structure"]
            .sudo()
            ._read_group(
                domain=[("rule_ids.code", "=", "EXPENSES")],
                groupby=["country_id"],
            )
        }

    def action_refuse(self):
        res = super().action_refuse()
        self.sudo().refund_in_payslip = (
            False
        )
        return res

    def action_reset(self):
        if any(slip.state in {"validated", "paid"} for slip in self.payslip_id):
            raise UserError(
                self.env._(
                    "You cannot remove an expense from a payslip that has already been validated.\n"
                    "Expenses can only be removed from draft or canceled payslips."
                )
            )
        self.sudo().action_remove_from_payslip()
        return super().action_reset()

    def action_report_in_next_payslip(self) -> None:
        if not self:
            raise UserError(self.env._("There are no valid expenses selected."))
        if self.filtered(
            lambda expense: (
                expense.state not in {"approved", "posted"}
                or expense.payment_mode != "own_account"
            )
        ):
            raise UserError(
                self.env._(
                    "Only approved and posted expenses that were paid by an employee can be reimbursed in a payslip."
                )
            )

        expense_structure_country_ids = self._get_countries_allowing_payslips()
        if (
            False not in expense_structure_country_ids
        ):
            for country_id in self.grouped(
                lambda expense: expense.company_id.country_id.id
            ):
                if country_id not in expense_structure_country_ids:
                    msg = self.env._(
                        "Expense reimbursement rule needs to be configured to add expenses to payslips.\n"
                        'Please create one salary rule with the "%(code)s" code on the relevant salary structures.',
                        code="EXPENSES",
                    )
                    action = self.env.ref(
                        "hr_payroll.action_salary_rule_form", raise_if_not_found=False
                    )
                    HrSalaryRule = self.env["hr.salary.rule"]
                    if HrSalaryRule.check_access("write") and action:
                        raise RedirectWarning(
                            message=msg,
                            action=action.id,
                            button_text=self.env._("Go to salary rules"),
                        )
                    raise UserError(msg)

        to_report = self.filtered(lambda expense: not expense.refund_in_payslip)
        to_report.refund_in_payslip = True
        for record in to_report:
            record.message_post(
                body=self.env._(
                    'Expense ("%(name)s") will be added to the next payslip.',
                    name=record.name,
                ),
                partner_ids=record.employee_id.user_id.partner_id.ids,
                email_layout_xmlid="mail.mail_notification_light",
                subtype_id=self.env["ir.model.data"]._xmlid_to_res_id("mail.mt_note"),
            )

    def action_remove_from_payslip(self) -> None:
        valid_expenses = self.filtered(
            lambda expense: (
                not expense.payslip_id
                or (
                    not expense.payslip_id.move_id
                    and expense.payslip_id.state in {"draft", "cancel"}
                )
            )
        )
        if not valid_expenses:
            raise UserError(
                self.env._(
                    "You cannot remove an expense from a payslip that has already been validated.\n"
                    "Expenses can only be removed from draft or canceled payslips."
                )
            )
        previous_payslips = valid_expenses.payslip_id
        expenses_to_edit = valid_expenses.filtered(
            lambda expense: expense.payslip_id or expense.refund_in_payslip
        )
        for expense in expenses_to_edit:
            expense.message_post(
                body=self.env._(
                    'Expense ("%(name)s") was removed from the next payslip.',
                    name=expense.name,
                ),
                partner_ids=expense.employee_id.user_id.partner_id.ids,
                email_layout_xmlid="mail.mail_notification_light",
                subtype_id=expense.env["ir.model.data"]._xmlid_to_res_id(
                    "mail.mt_note"
                ),
            )
        expenses_to_edit.write({"refund_in_payslip": False, "payslip_id": False})
        if previous_payslips:
            previous_payslips._update_expense_input_line_ids()

    def action_view_payslip(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Payslip"),
            "res_model": "hr.payslip",
            "view_mode": "form",
            "res_id": self.payslip_id.id,
        }

    def write(self, vals):
        if (
            vals.get("refund_in_payslip")
            and not self.env.user.has_groups(
                "account.group_account_invoice,hr_payroll.group_hr_payroll_user,"
            )
            and not self.env.su
        ):
            raise UserError(
                self.env._(
                    "You do not have permission to add this expense to a payslip."
                )
            )
        return super().write(vals)
