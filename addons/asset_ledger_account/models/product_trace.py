from typing import Any

from odoo import fields, models


class ProductTrace(models.Model):
    _inherit = "product.trace"

    account_move_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="trace_id",
        string="Bill Lines",
        export_string_translation=False,
    )

    def action_view_bills(self) -> dict[str, Any]:
        self.check_singleton()
        return self.asset_id.action_view_bills()
