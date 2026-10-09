from odoo import api, fields, models

UNCONFIRMED = ("pending", "unreachable", "expired", "disputed")


class AccountCollectionRemittance(models.Model):
    _inherit = "account.collection.remittance"

    count_payment_unconfirmed = fields.Integer(
        string="Not Confirmed by the Customer",
        compute="_compute_count_payment_unconfirmed",
        help="Collections in this remittance whose customer has not confirmed "
        "them: still waiting, unreachable, unanswered or disputed.",
    )
    count_payment_disputed = fields.Integer(
        string="Disputed by the Customer",
        compute="_compute_count_payment_unconfirmed",
    )

    @api.depends("payment_ids.confirmation_state")
    def _compute_count_payment_unconfirmed(self) -> None:
        for remittance in self:
            states = remittance.payment_ids.mapped("confirmation_state")
            remittance.count_payment_unconfirmed = sum(
                state in UNCONFIRMED for state in states
            )
            remittance.count_payment_disputed = states.count("disputed")
