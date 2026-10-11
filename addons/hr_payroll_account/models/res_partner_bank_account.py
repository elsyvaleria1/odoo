from odoo import Command, api, fields, models


class ResPartnerBankAccount(models.Model):
    _inherit = "res.partner.bank.account"

    has_alt_bank_account = fields.Boolean(compute="_compute_has_alt_bank_account")

    @api.depends("partner_id", "partner_id.bank_account_ids")
    def _compute_has_alt_bank_account(self) -> None:
        for bank_partner in self:
            if partner := bank_partner.partner_id:
                bank_partner.has_alt_bank_account = any(
                    bank != bank_partner for bank in partner.bank_account_ids
                )
            else:
                bank_partner.has_alt_bank_account = False

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        if self.env.context.get("from_employee_bank_account"):
            res._set_bank_account()
        return res

    def write(self, vals):
        previous_partners = (
            {bank: bank.partner_id for bank in self}
            if self.env.context.get("from_employee_bank_account")
            and "partner_id" in vals
            else None
        )
        res = super().write(vals)
        if previous_partners is not None:
            self._unset_bank_account(previous_partners)
            self._set_bank_account()
        return res

    def _set_bank_account(self) -> None:
        for partner_bank in self:
            partner_bank.partner_id.employee_ids.write(
                {"salary_bank_account_ids": [Command.link(partner_bank.id)]}
            )

    def _unset_bank_account(self, partners_by_bank) -> None:
        for partner_bank in self:
            previous_partner = partners_by_bank.get(partner_bank)
            if not previous_partner or previous_partner == partner_bank.partner_id:
                continue
            stale_employees = (
                previous_partner.employee_ids - partner_bank.partner_id.employee_ids
            )
            stale_employees.write(
                {"salary_bank_account_ids": [Command.unlink(partner_bank.id)]}
            )
