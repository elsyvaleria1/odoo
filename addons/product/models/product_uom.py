from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict


class ProductUom(models.Model):
    _name = "product.uom"
    _description = "Link between products and their UoMs"
    _rec_name = "barcode"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", hierarchy="parent_of"),
        }
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        index=True,
        required=True,
        ondelete="cascade",
        check_company=True,
    )
    uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        index=True,
        required=True,
        ondelete="cascade",
    )
    barcode = fields.Char(
        index="btree_not_null",
        copy=False,
        required=True,
    )

    _barcode_company_uniq = models.UniqueIndex(
        "(barcode, company_id) NULLS NOT DISTINCT",
        "A barcode can only be assigned to one packaging within a company.",
    )

    @api.constrains("barcode", "company_id")
    def _check_barcode_uniqueness(self) -> None:
        barcodes = [packaging.barcode for packaging in self if packaging.barcode]
        if not barcodes:
            return
        domain = [("barcode", "in", barcodes)]
        fnames = ["barcode", "company_id"]
        all_companies = self.sudo().env
        holders = [
            *all_companies["product.product"].search_fetch(domain, fnames),
            *all_companies["product.uom"].search_fetch(domain, fnames),
        ]
        for packaging in self:
            for holder in holders:
                if (
                    holder.barcode == packaging.barcode
                    and holder != packaging
                    and (
                        not holder.company_id
                        or not packaging.company_id
                        or holder.company_id == packaging.company_id
                    )
                ):
                    raise ValidationError(
                        self.env._(
                            "The barcode %s is already used by another product or"
                            " packaging.",
                            packaging.barcode,
                        )
                    )

    def _compute_display_name(self):
        if not self.env.context.get("show_variant_name"):
            return super()._compute_display_name()
        for record in self:
            record.display_name = (
                f"{record.barcode} for: {record.product_id.display_name}"
            )
        return None
