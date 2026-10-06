from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ApprovalRequestLine(models.Model):
    _inherit = "approval.request.line"

    purchase_order_line_id = fields.Many2one(
        comodel_name="purchase.order.line",
        index=True,
        copy=False,
        readonly=True,
        help="Link to the purchase order line created from this approval line",
    )
    purchase_order_id = fields.Many2one(
        comodel_name="purchase.order",
        related="purchase_order_line_id.order_id",
        string="Purchase Order",
        readonly=True,
        help="Purchase order that contains the line created from this approval",
    )
    seller_id = fields.Many2one(
        comodel_name="product.supplierinfo",
        string="Vendor",
        help="Manually select the vendor for this product. "
        "If not set, the system will automatically select a vendor during PO creation.",
    )
    product_uom_qty = fields.Float(
        string="Quantity in Product UoM",
        compute="_compute_product_uom_qty",
        help="Line quantity converted to the product's reference unit of "
        "measure. It is what the vendor lookup compares against the "
        "supplierinfo minimum quantity.",
    )

    @api.depends(
        "product_id",
        "quantity",
        "product_uom_id",
        "approval_request_id.target_model",
    )
    def _compute_product_uom_qty(self) -> None:
        for line in self:
            if (
                line.approval_request_id.target_model == "purchase.order"
                and line.product_id
                and line.quantity
            ):
                uom = line.product_uom_id or line.product_id.uom_id
                line.product_uom_qty = uom._get_quantity_report(
                    line.quantity,
                    line.product_id.uom_id,
                )
            else:
                line.product_uom_qty = 0.0

    def _is_seller_of_product(self) -> bool:
        self.check_singleton()
        seller_products = self.seller_id.product_id or (
            self.seller_id.product_tmpl_id.product_variant_ids
        )
        return self.product_id in seller_products

    @api.constrains("seller_id", "product_id")
    def _check_seller_matches_product(self) -> None:
        for line in self:
            if not line.seller_id:
                continue
            if not line._is_seller_of_product():
                raise ValidationError(
                    self.env._(
                        "The selected vendor pricelist line belongs to "
                        "%(seller_product)s, not to %(product)s. Pick a vendor "
                        "configured on the line's own product.",
                        seller_product=line.seller_id.product_tmpl_id.display_name,
                        product=line.product_id.display_name,
                    ),
                )

    @api.onchange("product_id")
    def _onchange_product_id_clear_seller(self) -> None:
        for line in self:
            if line.seller_id and not line._is_seller_of_product():
                line.seller_id = False

    def _get_fields_line_system(self) -> frozenset[str]:
        return super()._get_fields_line_system() | {"purchase_order_line_id"}

    def _check_products_vendor(self) -> None:
        lines_without_vendor = self.env["approval.request.line"]

        for line in self:
            if line.seller_id:
                continue

            if not line.product_id:
                continue

            has_vendor = bool(
                line.product_id.with_company(line.company_id)._select_seller(
                    quantity=line.product_uom_qty,
                    uom_id=line.product_id.uom_id,
                )
            )

            if not has_vendor:
                lines_without_vendor |= line

        if lines_without_vendor:
            product_names = lines_without_vendor.mapped("product_id.display_name")
            raise UserError(
                self.env._(
                    "No vendor can supply the requested quantity of the "
                    "product(s): %s.\n\nSelect a vendor on the approval line, or "
                    "configure one on the product whose minimum quantity the "
                    "line satisfies.",
                    ", ".join(product_names),
                )
            )
