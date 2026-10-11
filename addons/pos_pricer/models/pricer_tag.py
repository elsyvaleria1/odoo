import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

PRICER_TAG_ID_LENGTH = 17


class PricerTag(models.Model):
    _name = "pricer.tag"
    _description = "Pricer electronic tag"

    name = fields.Char(
        string="Pricer Tag Barcode ID",
        required=True,
        help="It is recommended to use a barcode scanner for input",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Associated Product",
        index=True,
        required=True,
        ondelete="cascade",
    )
    pricer_store_id = fields.Many2one(
        comodel_name="pricer.store",
        related="product_id.pricer_store_id",
        string="Associated Pricer Store",
        required=True,
        ondelete="cascade",
    )

    pricer_product_to_link = fields.Boolean(default=True)


    _name_unique = models.Constraint(
        "unique (name)",
        "A Pricer tag with this barcode id already exists",
    )

    @api.constrains("name")
    def _check_tag_id(self) -> None:
        for record in self:
            tag_id = record.name
            if (
                len(tag_id) != PRICER_TAG_ID_LENGTH
                or not tag_id[0].isalpha()
                or not tag_id[1:].isdigit()
            ):
                raise ValidationError(
                    self.env._(
                        "Tag id should be a 17 characters string composed of a letter followed by 16 digits"
                    )
                )


    def write(self, vals):
        if "product_id" in vals:
            vals["pricer_product_to_link"] = True
        return super().write(vals)


    @api.ondelete(at_uninstall=True)
    def _unlink_product_on_delete(self) -> None:
        for record in self:
            record.pricer_store_id.unlink_label(record.name)

    def _get_link_body(self) -> dict:
        return {
            "barcode": self.name,
            "links": [
                {
                    "barcode": self.name,
                    "itemId": self.product_id.id,
                }
            ],
        }
