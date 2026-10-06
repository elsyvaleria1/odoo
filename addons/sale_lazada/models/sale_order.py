from odoo import api, fields, models

from odoo.addons.sale_lazada import utils


class SaleOrder(models.Model):
    _inherit = "sale.order"

    lazada_order_ref = fields.Char(
        string="Lazada Reference",
        copy=False,
        readonly=True,
        help="The Lazada-defined order reference.",
    )
    lazada_shop_id = fields.Many2one(
        comodel_name="lazada.shop",
        index="btree_not_null",
        copy=False,
        help="The Lazada shop from which the order was placed.",
    )
    lazada_order_status = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("processing", "Processing"),
            ("delivered", "Delivered"),
            ("canceled", "Canceled"),
            ("manual", "Manual"),
        ],
        string="Lazada Status",
        compute="_compute_lazada_order_status",
    )
    lazada_fulfillment_type = fields.Selection(
        selection=[
            ("fbm", "Fulfillment by Merchant"),
            ("fbl", "Fulfillment by Lazada"),
        ],
        copy=False,
    )

    _unique_lazada_order_ref_lazada_shop_id = models.Constraint(
        "UNIQUE(lazada_order_ref, lazada_shop_id)",
        "There can only exist one sale order for a given Lazada Order Reference per Shop.",
    )

    @api.depends("picking_ids.lazada_package_status")
    def _compute_lazada_order_status(self) -> None:
        """Compute delivery status from Lazada order item statuses."""
        for order in self:
            package_statuses = order.picking_ids.mapped("lazada_package_status")
            order.lazada_order_status = utils.get_lazada_aggregated_status(
                package_statuses
            )
