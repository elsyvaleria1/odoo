from odoo import api, models


class ResourceAssetLog(models.Model):
    _inherit = "resource.asset.log"

    @api.depends(
        "account_move_line_id.non_deductible_tax_value",
        "account_move_line_id.account_id.multiple_assets_per_line",
    )
    def _compute_amount(self):
        super()._compute_amount()
        for log in self.filtered("account_move_line_id"):
            line = log.account_move_line_id
            quantity = line.quantity if line.account_id.multiple_assets_per_line else 1
            sign = -1 if line.balance < 0 else 1
            log.amount = line.currency_id.round(
                (line.balance + sign * line.non_deductible_tax_value) / (quantity or 1)
            )
