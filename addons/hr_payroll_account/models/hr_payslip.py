from collections import defaultdict

from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_compare, float_is_zero, plaintext2html
from odoo.tools.misc import format_date

_debug = DebugLog(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    date = fields.Date(
        string="Date Account",
        help="Keep empty to use the period of the validation(Payslip) date.",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        related="struct_id.journal_id",
        string="Salary Journal",
        check_company=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Accounting Entry",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )
    move_state = fields.Selection(
        related="move_id.state",
        string="Move State",
        export_string_translation=False,
    )
    batch_payroll_move_lines = fields.Boolean(
        related="company_id.batch_payroll_move_lines"
    )

    @api.model
    def _issues_dependencies(self):
        return super()._issues_dependencies() + ["struct_id.journal_id"]

    def _get_warnings_by_slip(self):
        warnings_by_slip = super()._get_warnings_by_slip()
        for slip in self.filtered(
            lambda slip: (
                slip.state in ["draft", "validated"]
                and slip.struct_id
                and not slip.with_company(slip.company_id).journal_id
            )
        ):
            warnings_by_slip[slip].append(
                {
                    "message": self.env._(
                        "Account Journal not configured on Structure"
                    ),
                    "action_text": self.env._("Structure"),
                    "action": slip.struct_id._get_records_action(target="new"),
                    "level": "warning",
                }
            )
        return warnings_by_slip

    def action_payslip_cancel(self):
        moves = self.mapped("move_id")
        _debug.lifecycle("cancel_unlinks_moves", payslips=self, moves=moves)
        moves.sudo()._unlink_or_reverse()
        _debug.logic(
            "stale_move_reference_cleared",
            payslips=self.filtered(lambda slip: slip.move_id.exists()),
        )
        self.filtered(lambda slip: slip.move_id.exists()).write({"move_id": False})
        return super().action_payslip_cancel()

    def action_payslip_done(self):
        if any(slip.state == "paid" for slip in self):
            _debug.logic("move_refused", reason="payslip_paid", payslips=self)
            raise ValidationError(
                self.env._("You can't create a journal entry for a paid payslip.")
            )
        res = super().action_payslip_done()
        for company, slips in self.grouped("company_id").items():
            slips = slips.with_company(company)
            slips.filtered("journal_id")._action_create_account_move()
        return res

    def _action_create_account_move(self) -> bool:
        precision = self.env["decimal.precision"].get_precision("Payroll")

        all_payslips = self
        for run in self.payslip_run_id:
            if run._are_payslips_ready():
                all_payslips |= run.slip_ids

        _debug.pipeline("account_moves", requested=self, with_batch_peers=all_payslips)
        payslips_to_post = all_payslips.filtered(
            lambda slip: (
                slip.state == "validated"
                and not slip.move_id
                and slip.struct_id.journal_id
            )
        )

        all_slip_mapped_data = []
        for company, company_slips in payslips_to_post.grouped("company_id").items():
            if company.batch_payroll_move_lines:
                company_mapped_data = defaultdict(
                    lambda: defaultdict(lambda: self.env["hr.payslip"])
                )
                for slip in company_slips:
                    company_mapped_data[slip.struct_id.journal_id.id][
                        slip.date or fields.Date.end_of(slip.date_to, "month")
                    ] |= slip
                all_slip_mapped_data.append(company_mapped_data)
            else:
                all_slip_mapped_data.extend(
                    {
                        slip.struct_id.journal_id.id: {
                            slip.date or fields.Date.end_of(slip.date_to, "month"): slip
                        }
                    }
                    for slip in company_slips
                )

        account_move_vals = []
        slips_date_tuples = []
        for slip_mapped_data in all_slip_mapped_data:
            for journal_id in slip_mapped_data:
                for slip_date in slip_mapped_data[journal_id]:
                    line_ids = []
                    debit_sum = 0.0
                    credit_sum = 0.0
                    date = slip_date
                    representative_slip = slip_mapped_data[journal_id][slip_date][0]
                    move_dict = {
                        "narration": "",
                        "ref": format_date(
                            self.env,
                            fields.Date.end_of(representative_slip.date_to, "month"),
                            lang_code=representative_slip.company_id.partner_id.lang,
                            date_format="MMMM y",
                        ),
                        "journal_id": journal_id,
                        "date": date,
                    }

                    for slip in slip_mapped_data[journal_id][slip_date]:
                        move_dict["narration"] += plaintext2html(
                            f"{slip.id or ''} - {slip.employee_id.name or ''}"
                        )
                        move_dict["narration"] += Markup("<br/>")
                        slip_lines = slip._prepare_slip_lines(date, line_ids)
                        line_ids.extend(slip_lines)

                    for line_id in line_ids:
                        debit_sum += line_id["debit"]
                        credit_sum += line_id["credit"]

                    if (
                        float_compare(credit_sum, debit_sum, precision_digits=precision)
                        == -1
                    ):
                        representative_slip._prepare_adjust_line(
                            line_ids, "credit", debit_sum, credit_sum, date
                        )
                    elif (
                        float_compare(debit_sum, credit_sum, precision_digits=precision)
                        == -1
                    ):
                        representative_slip._prepare_adjust_line(
                            line_ids, "debit", debit_sum, credit_sum, date
                        )

                    move_dict["line_ids"] = [
                        Command.create(line_vals) for line_vals in line_ids
                    ]
                    account_move_vals.append(move_dict)
                    slips_date_tuples.append(
                        (slip_mapped_data[journal_id][slip_date], date)
                    )
        moves = self._create_account_move(account_move_vals)
        for move, (slips, date) in zip(moves, slips_date_tuples, strict=False):
            slips.write({"move_id": move.id, "date": date})
            if slips.company_id.batch_payroll_move_lines:
                slips.payslip_run_id.write({"move_id": move.id})
        return True

    def _prepare_line_values(self, line, account, date, debit, credit, is_debit=None):
        if is_debit is None:
            is_debit = account.id == line.salary_rule_id.account_debit.id
        batch_lines = self.company_id.batch_payroll_move_lines
        if not batch_lines and line.salary_rule_id.employee_move_line:
            partner = self.employee_id.partner_id
        else:
            partner = line.partner_id
        line_vals = []
        if (
            not batch_lines
            and line.salary_rule_id.employee_move_line
            and self.employee_id.has_multiple_bank_accounts
        ):
            try:
                debit_allocations = self.compute_salary_allocations(debit)
                credit_allocations = self.compute_salary_allocations(credit)
            except ValidationError as error:
                raise ValidationError(
                    self.env._(
                        "The bank account split of %(employee)s cannot be applied"
                        " to the %(rule)s line of payslip %(payslip)s"
                        " (debit %(debit)s, credit %(credit)s): %(reason)s",
                        employee=self.employee_id.name,
                        rule=line.salary_rule_id.name,
                        payslip=self.name,
                        debit=debit,
                        credit=credit,
                        reason=error.args[0] if error.args else error,
                    )
                ) from error
            for ba in self.employee_id.salary_bank_account_ids:
                subdebit = debit_allocations.get(str(ba.id), 0)
                subcredit = credit_allocations.get(str(ba.id), 0)
                if self.currency_id.is_zero(subdebit) and self.currency_id.is_zero(
                    subcredit
                ):
                    continue
                line_vals.append(
                    {
                        "name": line.name
                        if line.salary_rule_id.split_move_lines
                        else line.salary_rule_id.name,
                        "partner_id": partner.id,
                        "account_id": account.id,
                        "employee_bank_account_id": ba.id,
                        "journal_id": line.slip_id.struct_id.journal_id.id,
                        "date": date,
                        "debit": subdebit,
                        "credit": subcredit,
                        "analytic_distribution": line.salary_rule_id.analytic_distribution
                        or line.slip_id.version_id.analytic_distribution,
                        "tax_tag_ids": line.debit_tag_ids.ids
                        if is_debit
                        else line.credit_tag_ids.ids,
                        "tax_ids": [
                            Command.link(tax_id) for tax_id in account.tax_ids.ids
                        ],
                    }
                )
            return line_vals

        return [
            {
                "name": line.name
                if line.salary_rule_id.split_move_lines
                else line.salary_rule_id.name,
                "partner_id": partner.id,
                "account_id": account.id,
                "journal_id": line.slip_id.struct_id.journal_id.id,
                "date": date,
                "debit": debit,
                "credit": credit,
                "analytic_distribution": line.salary_rule_id.analytic_distribution
                or line.slip_id.version_id.analytic_distribution,
                "tax_tag_ids": line.debit_tag_ids.ids
                if is_debit
                else line.credit_tag_ids.ids,
                "tax_ids": [Command.link(tax_id) for tax_id in account.tax_ids.ids],
            }
        ]

    def _prepare_slip_lines(self, date, line_ids):
        self.check_singleton()
        precision = self.env["decimal.precision"].get_precision("Payroll")
        new_lines = []
        existing_by_key = defaultdict(list)
        for existing_line in line_ids:
            existing_by_key[
                (existing_line["name"], existing_line["account_id"])
            ].append(existing_line)

        category_lines = self.line_ids.filtered(lambda line: line.category_id)
        for line in category_lines:
            amount = line.total
            if line.code == "NET":
                for tmp_line in category_lines:
                    if (
                        tmp_line.id != line.id
                        and tmp_line.salary_rule_id.not_computed_in_net
                    ):
                        amount -= tmp_line.total
            if float_is_zero(amount, precision_digits=precision):
                continue
            debit_account = line.salary_rule_id.account_debit
            credit_account = line.salary_rule_id.account_credit
            merge_amounts = (
                self.company_id.batch_payroll_move_lines
                or not line.salary_rule_id.employee_move_line
            )

            if debit_account.id:
                if (
                    self.company_id.account_config_id.account_storno
                    and self.credit_note
                ):
                    debit = min(0.0, amount)
                    credit = -amount if amount > 0.0 else 0.0
                else:
                    debit = max(0.0, amount)
                    credit = -amount if amount < 0.0 else 0.0

                debit_name = (
                    line.name
                    if line.salary_rule_id.split_move_lines
                    else line.salary_rule_id.name
                )
                debit_line = merge_amounts and next(
                    self._get_existing_lines(
                        existing_by_key[(debit_name, debit_account.id)],
                        line,
                        debit_account.id,
                        debit,
                        credit,
                        is_debit=True,
                    ),
                    False,
                )

                if not debit_line:
                    debit_lines = self._prepare_line_values(
                        line, debit_account, date, debit, credit, is_debit=True
                    )
                    new_lines.extend(debit_lines)
                    for new_line in debit_lines:
                        existing_by_key[
                            (new_line["name"], new_line["account_id"])
                        ].append(new_line)
                else:
                    debit_line["debit"] += debit
                    debit_line["credit"] += credit

            if credit_account.id:
                if (
                    self.company_id.account_config_id.account_storno
                    and self.credit_note
                ):
                    debit = -amount if amount > 0.0 else 0.0
                    credit = min(0.0, amount)
                else:
                    debit = -amount if amount < 0.0 else 0.0
                    credit = max(0.0, amount)

                credit_name = (
                    line.name
                    if line.salary_rule_id.split_move_lines
                    else line.salary_rule_id.name
                )
                credit_line = merge_amounts and next(
                    self._get_existing_lines(
                        existing_by_key[(credit_name, credit_account.id)],
                        line,
                        credit_account.id,
                        debit,
                        credit,
                        is_debit=False,
                    ),
                    False,
                )

                if not credit_line:
                    credit_lines = self._prepare_line_values(
                        line, credit_account, date, debit, credit, is_debit=False
                    )
                    new_lines.extend(credit_lines)
                    for new_line in credit_lines:
                        existing_by_key[
                            (new_line["name"], new_line["account_id"])
                        ].append(new_line)
                else:
                    credit_line["debit"] += debit
                    credit_line["credit"] += credit
        return new_lines

    def _prepare_adjust_line(
        self, line_ids, adjust_type, debit_sum, credit_sum, date
    ) -> None:
        acc_id = self.sudo().journal_id.default_account_id.id
        if not acc_id:
            raise UserError(
                self.env._(
                    'The Expense Journal "%s" has not properly configured the default Account!',
                    self.journal_id.name,
                )
            )
        line_ids.append(
            {
                "name": self.env._("Adjustment Entry"),
                "partner_id": False,
                "account_id": acc_id,
                "journal_id": self.journal_id.id,
                "date": date,
                "debit": 0.0 if adjust_type == "credit" else credit_sum - debit_sum,
                "credit": debit_sum - credit_sum if adjust_type == "credit" else 0.0,
            }
        )

    def _has_matching_debit_credit_tags(self, line_vals, line, is_debit) -> bool:
        tag_ids = line.debit_tag_ids.ids if is_debit else line.credit_tag_ids.ids
        return sorted(line_vals["tax_tag_ids"]) == sorted(tag_ids)

    def _get_existing_lines(self, line_ids, line, account_id, debit, credit, is_debit):
        return (
            line_id
            for line_id in line_ids
            if line_id["name"]
            == (
                line.name
                if line.salary_rule_id.split_move_lines
                else line.salary_rule_id.name
            )
            and line_id["account_id"] == account_id
            and (
                (line_id["debit"] > 0 and credit <= 0)
                or (line_id["credit"] > 0 and debit <= 0)
            )
            and self._has_matching_analytic_distribution(line_id, line)
            and self._has_matching_debit_credit_tags(line_id, line, is_debit)
        )

    def _has_matching_analytic_distribution(self, line_vals, line) -> bool:
        expected = (
            line.salary_rule_id.analytic_distribution
            or line.slip_id.version_id.analytic_distribution
        )
        return (line_vals["analytic_distribution"] or False) == (expected or False)

    def _create_account_move(self, values):
        return self.env["account.move"].sudo().create(values)

    def action_register_payment(self):
        self.check_singleton()
        if any(state == "paid" for state in self.mapped("state")):
            raise UserError(
                self.env._("You can only register payments for unpaid documents.")
            )
        net_rules = self.with_company(self.company_id).struct_id.rule_ids.filtered(
            lambda r: r.code == "NET"
        )
        if not net_rules:
            raise UserError(
                self.env._(
                    "The salary structure %s has no rule with the code NET,"
                    " so there is no account to register the payment against.",
                    self.struct_id.name,
                )
            )
        if len(net_rules) > 1:
            raise UserError(
                self.env._(
                    "The salary structure %s has more than one rule with the"
                    " code NET. Payroll cannot tell which one carries the"
                    " account to pay from.",
                    self.struct_id.name,
                )
            )
        if not net_rules.account_credit.reconcile:
            raise UserError(
                self.env._(
                    "The credit account on the NET salary rule is not reconciliable"
                )
            )
        bank_accounts = (
            self.move_id.line_ids.employee_bank_account_id
            or self.employee_id.primary_bank_account_id
        ).sudo()
        if any(not bank.allow_out_payment for bank in bank_accounts):
            raise UserError(self.env._("An employee bank account is untrusted"))
        if any(m.state != "posted" for m in self.move_id):
            raise UserError(
                self.env._("You can only register payment for posted journal entries.")
            )
        return self.move_id.line_ids.action_register_payment(
            ctx={
                "default_partner_id": self.employee_id.partner_id.id,
                "default_bank_account_id": self.employee_id.primary_bank_account_id.id,
                "default_company_id": self.company_id.id,
                "payment_consider_partner": True,
            }
        )

    def action_view_move(self) -> dict:
        self.check_singleton()
        if not self.move_id:
            raise UserError(self.env._("This payslip has no journal entry to display."))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Journal Entry"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
        }
