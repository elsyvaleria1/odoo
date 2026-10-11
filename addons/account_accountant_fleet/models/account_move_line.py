from odoo import api, models
from odoo.tools import SQL


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def _get_base_tax_line_mapping_conditions(self) -> list[SQL]:
        return [
            *super()._get_base_tax_line_mapping_conditions(),
            SQL(
                "COALESCE(base_line.asset_id, 0)"
                " = COALESCE(account_move_line.asset_id, 0)"
            ),
        ]
