from odoo import models
from odoo.exceptions import AccessError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post_entries(self):
        lines_to_reconcile = self.env["account.move.line"]
        if (
            not self.env.context.get("skip_reconcile_expense_with_payslip")
            and self.sudo().payslip_ids.expense_ids
        ):
            self = self.with_context(
                skip_reconcile_expense_with_payslip=True
            )
            lines_to_reconcile = (
                self._hr_payroll_expense_prepare_move_lines_to_reconcile()
            )

        res = (
            super()._post_entries()
        )

        lines_to_reconcile = lines_to_reconcile.filtered(
            lambda line: not line.reconciled
        )
        if lines_to_reconcile:
            wizard = (
                self.env["wizard.account.move.line.reconcile"]
                .with_context(
                    active_model="account.move.line",
                    active_ids=lines_to_reconcile.ids,
                )
                .new({})
            )
            if not (
                wizard.is_write_off_required or wizard.force_partials
            ):
                wizard.reconcile()
        return res

    def unlink(self):
        moves_to_unlink_ids = self.sudo().payslip_ids.expense_ids.account_move_id.ids
        if moves_to_unlink_ids:
            self.browse(moves_to_unlink_ids)._unlink_or_reverse()
        return super().unlink()

    def _hr_payroll_expense_prepare_move_lines_to_reconcile(self):
        if not self.env.is_superuser() and not self.env.user.has_group(
            "account.group_account_invoice"
        ):
            raise AccessError(
                self.env._("You don't have the access rights to post an invoice.")
            )

        payslips_sudo = self.sudo().payslip_ids
        all_payslip_expenses_sudo = payslips_sudo.expense_ids
        if not all_payslip_expenses_sudo:
            return self.env[
                "account.move.line"
            ]

        expenses_without_moves = all_payslip_expenses_sudo.filtered(
            lambda expense: not expense.account_move_id
        )
        if expenses_without_moves:
            expenses_without_moves._post_without_wizard()

        payslip_move_to_expense_move_map = {}

        valid_expenses_sudo = all_payslip_expenses_sudo.filtered(
            lambda expense: expense.state == "posted"
        )
        for payslip_sudo, expenses_sudo in valid_expenses_sudo.grouped(
            "payslip_id"
        ).items():
            payslip_move_to_expense_move_map.setdefault(
                payslip_sudo.move_id, self.env["account.move"].sudo()
            )
            payslip_move_to_expense_move_map[payslip_sudo.move_id] |= (
                expenses_sudo.sorted().account_move_id
            )

        lines_to_reconcile_sudo = self.env["account.move.line"]
        rule_account_id_per_struct_id = (
            payslips_sudo.struct_id._get_expense_rule_account_id_map(
                payslips_sudo.company_id
            )
        )
        for idx, (payslip_move_sudo, expense_moves_sudo) in enumerate(
            payslip_move_to_expense_move_map.items()
        ):
            payslip_account_id = rule_account_id_per_struct_id[
                payslip_move_sudo.payslip_ids.struct_id.id
            ]
            lines_to_match_sudo = payslip_move_sudo.line_ids.filtered_domain(
                [
                    ("account_id", "=", payslip_account_id),
                    ("display_type", "!=", "payment_term"),
                ]
            )

            lines_to_match_sudo |= expense_moves_sudo.line_ids.filtered(
                lambda aml: aml.account_id.account_type == "liability_payable"
            )

            lines_to_match_sudo.matching_number = (
                f"{idx:0>10}-{payslip_move_sudo.id}-{min(expense_moves_sudo.ids)}"
            )
            lines_to_reconcile_sudo |= lines_to_match_sudo

        expense_moves_to_post_sudo = all_payslip_expenses_sudo.account_move_id.filtered(
            lambda move: move.state == "draft"
        )
        if expense_moves_to_post_sudo:
            expense_moves_to_post_sudo._post(soft=False)

        if len(lines_to_reconcile_sudo.account_id) > 2:
            return self.env["account.move.line"]

        return lines_to_reconcile_sudo.sorted(lambda line: abs(line.balance)).sudo(
            self.env.is_superuser()
        )
