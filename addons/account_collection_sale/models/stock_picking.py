from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_handed_over_at_sale = fields.Boolean(
        string="Handed Over at Sale",
        copy=False,
        readonly=True,
        help="The customer took the goods when the salesperson collected the cash "
        "sale; the transfer travelled in no delivery.",
    )

    def _prepare_hand_over_at_sale(self) -> None:
        pass

    def _hand_over_at_sale(self) -> None:
        self.move_ids.picked = True
        self.button_validate()
        if pending := self.filtered(lambda picking: picking.state != "done"):
            raise UserError(
                self.env._(
                    "%(pickings)s could not be handed over: validate them from "
                    "Inventory to see what they ask.",
                    pickings=", ".join(pending.mapped("name")),
                )
            )
