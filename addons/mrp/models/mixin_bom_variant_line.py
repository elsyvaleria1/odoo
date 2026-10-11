from itertools import product as cartesian_product
from itertools import starmap
from typing import Self

from odoo import api, fields, models


class MixinBomVariantLine(models.AbstractModel):
    _name = "mixin.bom.variant.line"
    _description = "BoM row that may be restricted to some variants"

    bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Parent BoM",
        index=True,
        required=True,
        ondelete="cascade",
    )
    possible_bom_product_template_attribute_value_ids = fields.Many2many(
        related="bom_id.possible_product_template_attribute_value_ids"
    )
    bom_product_template_attribute_value_ids = fields.Many2many(
        comodel_name="product.template.attribute.value",
        string="Apply on Variants",
        domain="[('id', 'in', possible_bom_product_template_attribute_value_ids)]",
        ondelete="restrict",
        help="BOM Product Variants needed to apply this line.",
    )

    @api.constrains("bom_id", "bom_product_template_attribute_value_ids")
    def _check_parent_bom(self) -> None:
        self.bom_id._check_bom_lines()

    def _is_bom_line_skipped(self, product, never_attribute_values=False) -> bool:
        self.check_singleton()
        if not product or product._name == "product.template":
            return False
        return bool(
            self._is_skipped_for_no_variant(
                product,
                self._get_variant_conditions(),
                never_attribute_values,
            )
        )

    def _get_variant_conditions(self):
        return self.bom_product_template_attribute_value_ids.filtered(
            lambda value: (
                value.product_attribute_value_id
                not in value.product_tmpl_id.specification_line_ids.value_ids
            )
        )

    def _is_skipped_for_no_variant(
        self, product, bom_attribute_values, never_attribute_values=False
    ) -> bool:
        no_variant_bom_attributes = bom_attribute_values.filtered(
            lambda av: av.attribute_id.create_variant == "no_variant"
        )
        other_attribute_valid = product._has_all_variant_values(
            bom_attribute_values - no_variant_bom_attributes
        )
        if not no_variant_bom_attributes:
            return not other_attribute_valid
        if not never_attribute_values:
            return True

        matched_attributes = (
            no_variant_bom_attributes & never_attribute_values
        ).attribute_id
        if matched_attributes != no_variant_bom_attributes.attribute_id:
            return True
        return not other_attribute_valid

    def _filtered_applicable_to(self, product, never_attribute_values=False) -> Self:
        return self.filtered(
            lambda row: not row._is_bom_line_skipped(product, never_attribute_values)
        )

    def _get_no_variant_values(self):
        return self._get_variant_conditions().filtered(
            lambda value: value.attribute_id.create_variant == "no_variant"
        )

    def _filtered_possibly_applicable_to(self, product):
        return self._filtered_applicable_to(product, self._get_no_variant_values())

    def _get_no_variant_choices(self):
        values = self._get_no_variant_values()
        options = [
            [attribute_values]
            if attribute.display_type == "multi"
            else list(attribute_values)
            for attribute, attribute_values in values.grouped("attribute_id").items()
        ]
        return list(starmap(values.browse().union, cartesian_product(*options)))
