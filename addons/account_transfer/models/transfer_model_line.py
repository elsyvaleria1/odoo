from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountTransferModelLine(models.Model):
    _name = "account.transfer.model.line"
    _description = "Account Transfer Model Line"
    _order = "sequence, id"

    transfer_model_id = fields.Many2one(
        comodel_name="account.transfer.model",
        index=True,
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Destination Account",
        domain="[('account_type', '!=', 'off_balance')]",
    )
    percent = fields.Float(
        default=100,
        required=True,
        help="Percentage of the sum of lines from the origin accounts will be transferred to the destination account",
    )
    sequence = fields.Integer()

    _unique_account_by_transfer_model = models.Constraint(
        "UNIQUE(transfer_model_id, account_id)",
        "Only one account occurrence by transfer model",
    )

    @api.constrains("account_id")
    def _check_account_id(self) -> None:
        """Check that there is a destination account set on each transfer model line and that it is unique."""
        for record in self:
            if not record.account_id:
                raise ValidationError(
                    self.env._("A destination account must be set on each line.")
                )
