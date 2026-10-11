from odoo import models


class PosCategory(models.Model):
    _inherit = "pos.category"

    def write(self, vals):
        if vals.get("sequence") or vals.get("name"):
            if linked_urbanpiper_status := self.env[
                "product.urban.piper.status"
            ].search(
                [
                    ("product_tmpl_id.pos_categ_ids", "in", self.ids),
                    ("is_product_linked", "=", True),
                ],
                limit=1,
            ):
                linked_urbanpiper_status.is_product_linked = False
        return super().write(vals)
