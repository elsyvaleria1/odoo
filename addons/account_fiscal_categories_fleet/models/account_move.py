from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends("account_id.fiscal_category_id")
    def _compute_need_asset(self) -> None:
        for record in self:
            record.need_asset = (
                record.account_id.fiscal_category_id.sudo().car_category
                and record.move_id.move_type == "in_invoice"
            )

    @api.model
    def _prepare_deferred_lines_values(
        self, account_id, balance, ref, analytic_distribution, line=None
    ) -> dict:
        deferred_lines_values = super()._prepare_deferred_lines_values(
            account_id, balance, ref, analytic_distribution, line
        )
        return {
            **deferred_lines_values,
            "asset_id": self._deferred_line_asset_id(line),
        }

    @api.model
    def _prepare_deferred_amounts_by_line_values(self, line):
        values = super()._prepare_deferred_amounts_by_line_values(line)
        values["asset_id"] = self._deferred_line_asset_id(line)
        return values

    @api.model
    def _deferred_line_asset_id(self, line):
        if not line or "asset_id" not in line:
            return None
        return int(line["asset_id"] or 0) or None
