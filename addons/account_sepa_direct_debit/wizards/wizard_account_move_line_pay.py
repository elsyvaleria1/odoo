from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class WizardAccountMoveLinePay(models.TransientModel):
    _inherit = "wizard.account.move.line.pay"

    no_sdd_mandate_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        compute="_compute_no_sdd_mandate_partner_ids",
    )

    @api.depends("payment_date", "partner_id", "company_id", "line_ids.partner_id")
    def _compute_no_sdd_mandate_partner_ids(self) -> None:
        for wizard in self:
            partners_with_valid_mandates = wizard._get_partner_ids_with_valid_mandates()
            wizard.no_sdd_mandate_partner_ids = wizard.line_ids.partner_id - self.env[
                "res.partner"
            ].browse(partners_with_valid_mandates)

    def _get_partner_ids_with_valid_mandates(self) -> set:
        self.check_singleton()
        moves_to_pay = self.line_ids.move_id
        valid_mandate_ids_per_partner_id = self.env["sdd.mandate"]._read_group(
            [
                ("state", "=", "active"),
                ("start_date", "<=", self.payment_date),
                "|",
                ("end_date", "=", False),
                ("end_date", ">=", self.payment_date),
                ("partner_id", "in", moves_to_pay.partner_id.commercial_partner_id.ids),
                *self.env["sdd.mandate"]._get_domain_company_compatible(
                    moves_to_pay.company_id
                ),
            ],
            groupby=["partner_id"],
        )
        return {partner.id for (partner,) in valid_mandate_ids_per_partner_id}

    def action_create_payments(self):
        sdd_codes = set(
            self.env["account.payment.method"]._get_sdd_payment_method_code()
        )

        for wizard in self.filtered(lambda wiz: wiz.payment_method_code in sdd_codes):
            valid_partner_ids = wizard._get_partner_ids_with_valid_mandates()
            if set(wizard.line_ids.partner_id.ids) != valid_partner_ids:
                wizard.write(
                    {
                        "line_ids": [
                            Command.set(
                                wizard.line_ids.filtered_domain(
                                    [("partner_id", "in", list(valid_partner_ids))]
                                ).ids
                            )
                        ],
                        "payment_channel_id": wizard.payment_channel_id.id,
                        "group_payment": wizard.group_payment,
                    }
                )
            if not wizard.line_ids:
                raise UserError(
                    self.env._(
                        "You can't pay any of the selected invoices using the SEPA Direct Debit method, as no valid mandate is available"
                    )
                )

        return super().action_create_payments()
