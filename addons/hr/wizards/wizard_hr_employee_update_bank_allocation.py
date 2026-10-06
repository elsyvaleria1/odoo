from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.libs.numbers import float_round

_debug = DebugLog(__name__)


class WizardHrEmployeeUpdateBankAllocation(models.TransientModel):
    _name = "wizard.hr.employee.update.bank.allocation"
    _description = "Bank Account Allocation Wizard"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
    )
    allocation_ids = fields.One2many(
        comodel_name="wizard.hr.employee.update.bank.allocation.line",
        inverse_name="wizard_id",
        string="Allocations",
        readonly=False,
    )

    def _update_allocations_from_employee(self) -> None:
        self.check_singleton()
        employee = self.employee_id
        allocations = employee.salary_allocation_ids
        allocated = {a.bank_account_id.id: a for a in allocations}
        next_seq = max(allocations.mapped("sequence"), default=-1)
        wizard_lines = []
        for account in employee.salary_bank_account_ids:
            allocation = allocated.get(account.id)
            if allocation:
                amount = allocation.amount
                is_percentage = allocation.amount_is_percentage
                sequence = allocation.sequence
            else:
                amount = 0.0
                is_percentage = True
                next_seq += 1
                sequence = next_seq
            wizard_lines.append(
                Command.create(
                    {
                        "bank_account_id": account.id,
                        "amount": amount,
                        "amount_type": "percentage" if is_percentage else "fixed",
                        "trusted": account.allow_out_payment,
                        "sequence": sequence,
                    }
                )
            )
        _debug.logic(
            "lines_from_allocations",
            wizard=self.id,
            employee=employee.id,
            lines=len(wizard_lines),
            allocations=len(allocations),
        )
        self.write({"allocation_ids": wizard_lines})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _debug.lifecycle("created", wizards=records, employees=records.employee_id)
        for wizard in records:
            wizard._update_allocations_from_employee()
        return records

    @_debug.perf.timed
    def action_save(self):
        self.check_singleton()

        precision_digits = 2

        values_by_account = {}
        seen_accounts = set()
        trust_by_account = {}

        for line in self.allocation_ids:
            bank_account = line.bank_account_id
            if bank_account.id in seen_accounts:
                raise ValidationError(
                    self.env._(
                        "Bank account %s is allocated on several lines; each"
                        " bank account can only be used once.",
                        bank_account.display_name,
                    )
                )
            seen_accounts.add(bank_account.id)
            values_by_account[bank_account.id] = {
                "amount": float_round(
                    line.amount,
                    precision_digits=precision_digits,
                    rounding_method="DOWN",
                ),
                "sequence": line.sequence,
                "amount_is_percentage": line.amount_type == "percentage",
            }
            trust_by_account[bank_account] = line.trusted

        _debug.logic(
            "lines_to_allocations", wizard=self.id, lines=len(self.allocation_ids)
        )

        trusted = self.env["res.partner.bank.account"]
        untrusted = self.env["res.partner.bank.account"]
        for account, is_trusted in trust_by_account.items():
            if is_trusted:
                trusted |= account
            else:
                untrusted |= account
        _debug.pipeline(
            "trust_updated", wizard=self.id, trusted=trusted, untrusted=untrusted
        )
        if trusted:
            trusted.sudo().write({"allow_out_payment": True})
        if untrusted:
            untrusted.sudo().write({"allow_out_payment": False})

        Allocation = self.env["hr.employee.bank.allocation"]
        existing = {
            a.bank_account_id.id: a for a in self.employee_id.salary_allocation_ids
        }
        for account_id, values in values_by_account.items():
            allocation = existing.pop(account_id, None)
            if allocation:
                allocation.write(values)
            else:
                Allocation.create(
                    {"employee_id": self.employee_id.id, "bank_account_id": account_id}
                    | values
                )
        if existing:
            Allocation.browse([a.id for a in existing.values()]).unlink()
        _debug.lifecycle(
            "allocations_replaced",
            wizard=self.id,
            employee=self.employee_id.id,
            rows=len(values_by_account),
        )
