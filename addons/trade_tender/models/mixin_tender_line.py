from odoo import api, fields, models
from odoo.tools import frozendict


class MixinTenderLine(models.AbstractModel):
    _name = "mixin.tender.line"
    _description = "Tender Need"
    _order = "tender_id, sequence, id"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("tender_id.company_id", shared=False),
        }
    )

    tender_id = fields.Many2one(
        comodel_name="mixin.tender",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="tender_id.company_id")
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        required=True,
        check_company=True,
    )
    description = fields.Char(
        help="What the offers must match beyond the product: grade, packing, origin.",
    )
    product_qty = fields.Float(
        string="Needed",
        digits="Product Unit",
        default=1.0,
        required=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        compute="_compute_product_uom_id",
        precompute=True,
        store=True,
        readonly=False,
    )
    date_needed = fields.Date(
        string="Needed By",
        help="The date the counterparty must meet: delivery when we buy, "
        "collection when we sell.",
    )
    offer_count = fields.Integer(
        string="Offers",
        compute="_compute_award",
        help="The open offers that quote this product.",
    )
    qty_awarded = fields.Float(
        string="Awarded",
        digits="Product Unit",
        compute="_compute_award",
        help="What the offers' awarded lines give of this need, in its unit.",
    )
    qty_to_award = fields.Float(
        string="To Award",
        digits="Product Unit",
        compute="_compute_award",
    )

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id

    @api.depends(
        "product_id",
        "product_qty",
        "product_uom_id",
        "tender_id.order_ids.outcome",
        "tender_id.order_ids.line_ids.qty_awarded",
    )
    def _compute_award(self) -> None:
        for line in self:
            offered = line.tender_id.order_ids.filtered(
                lambda order: order.outcome in ("open", "won")
            ).line_ids.filtered(
                lambda offer_line, product=line.product_id: (
                    offer_line.product_id == product and not offer_line.display_type
                )
            )
            line.offer_count = len(offered.order_id)
            line.qty_awarded = sum(
                offer_line.product_uom_id._get_quantity_in_unit(
                    offer_line.qty_awarded, line.product_uom_id
                )
                for offer_line in offered
            )
            line.qty_to_award = line.product_qty - line.qty_awarded

    def _prepare_offer_line_values(self):
        self.check_singleton()
        values = {
            "product_id": self.product_id.id,
            "product_qty": self.product_qty,
            "product_uom_id": self.product_uom_id.id,
        }
        if self.description:
            values["name"] = self.description
        return values

    @api.model
    def _prepare_values_from_order_line(self, order_line, date_needed) -> dict:
        return {
            "product_id": order_line.product_id.id,
            "product_qty": order_line.product_qty,
            "product_uom_id": order_line.product_uom_id.id,
            "date_needed": date_needed,
        }
