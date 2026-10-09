from typing import Self

from odoo import api, fields, models
from odoo.exceptions import UserError

from .utils import write_and_reorder


class ProductAttributeValue(models.Model):
    _name = "product.attribute.value"
    _inherit = "mixin.attribute.value"
    _order = "attribute_id, sequence, id"
    _description = "Attribute Value"

    attribute_id = fields.Many2one(
        comodel_name="product.attribute",
        index=True,
        required=True,
        ondelete="cascade",
        help="The attribute cannot be changed once the value is used on at least one product.",
    )
    display_type = fields.Selection(related="attribute_id.display_type")
    name = fields.Char(string="Value")
    sequence = fields.Integer(
        index=True,
        help="Determine the display order",
    )
    color = fields.Integer(string="Color Index")
    html_color = fields.Char(
        string="Color",
        help="Here you can set a specific HTML color index (e.g. #ff0000)"
        " to display the color if the attribute type is 'Color'.",
    )
    pav_attribute_line_ids = fields.Many2many(
        comodel_name="product.template.attribute.line",
        relation="product_attribute_value_product_template_attribute_line_rel",
        string="Lines",
        copy=False,
    )

    default_extra_price = fields.Float()
    image = fields.Image(
        max_width=70,
        max_height=70,
        help="You can upload an image that will be used as the color of the attribute value.",
    )

    is_custom = fields.Boolean(
        string="Free text",
        help="Allow customers to set their own value",
    )
    is_used_on_products = fields.Boolean(
        string="Used on Products",
        compute="_compute_is_used_on_products",
    )
    default_extra_price_changed = fields.Boolean(
        compute="_compute_default_extra_price_changed"
    )

    def _filtered_used(self):
        return self.filtered("is_used_on_products")

    def _usage_label(self) -> str:
        return ", ".join(
            self.pav_attribute_line_ids.product_tmpl_id.mapped("display_name")
        )

    def write(self, vals):
        if "attribute_id" in vals:
            self._check_not_carried_when_moved(vals["attribute_id"])
        return write_and_reorder(self, vals, super().write)

    def _check_not_carried_when_moved(self, attribute_id) -> None:
        carried = self.filtered(
            lambda pav: (
                pav.attribute_id.id != attribute_id and pav.pav_attribute_line_ids
            )
        )
        if carried:
            raise UserError(
                self.env._(
                    "You cannot change the attribute of %(names)s because it is"
                    " used on: %(usage)s",
                    names=", ".join(carried.mapped("display_name")),
                    usage=carried._usage_label(),
                )
            )

    def unlink(self):
        PTAV = self.env["product.template.attribute.value"].with_context(
            active_test=False
        )
        ptavs_by_pav = PTAV.search(
            [("product_attribute_value_id", "in", self.ids)]
        ).grouped("product_attribute_value_id")
        pavs_to_archive = self.env["product.attribute.value"]
        for pav in self:
            linked_products = ptavs_by_pav.get(pav, PTAV).ptav_product_variant_ids
            active_linked_products = linked_products.filtered("active")
            if (
                linked_products
                and not active_linked_products
                and not pav.is_used_on_products
            ):
                pavs_to_archive |= pav
        remaining = self - pavs_to_archive
        if remaining:
            still_referenced = remaining.with_context(active_test=False).filtered(
                lambda pav: pav.pav_attribute_line_ids and not pav.is_used_on_products
            )
            pavs_to_archive |= still_referenced.with_env(self.env)
        if pavs_to_archive:
            pavs_to_archive.action_archive()
        return super(ProductAttributeValue, self - pavs_to_archive).unlink()

    @api.depends("pav_attribute_line_ids")
    def _compute_is_used_on_products(self) -> None:
        for pav in self:
            pav.is_used_on_products = bool(
                pav.pav_attribute_line_ids.filtered("product_tmpl_id.active")
            )

    @api.depends("default_extra_price")
    def _compute_default_extra_price_changed(self) -> None:
        company_domain = self.env["product.template"]._check_company_domain(
            self.env.companies
        )
        ptavs_by_pav = (
            self.env["product.template.attribute.value"]
            .sudo()
            .search_fetch(
                [
                    ("product_attribute_value_id", "in", self.ids),
                    ("product_tmpl_id", "any", company_domain),
                ],
                ["price_extra", "product_attribute_value_id"],
            )
            .grouped("product_attribute_value_id")
        )
        for pav in self:
            ptavs = ptavs_by_pav.get(pav, [])
            pav.default_extra_price_changed = (
                pav.default_extra_price != pav._origin.default_extra_price
                or any(pav.default_extra_price != ptav.price_extra for ptav in ptavs)
            )

    @api.readonly
    def action_add_to_products(self) -> dict:
        return {
            "name": self.env._("Add to all products"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.product.attribute.value.propagate",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_attribute_value_id": self.id,
                "default_mode": "add",
                "dialog_size": "medium",
            },
        }

    @api.readonly
    def action_update_prices(self) -> dict | None:
        return {
            "name": self.env._("Update product extra prices"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.product.attribute.value.propagate",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_attribute_value_id": self.id,
                "default_mode": "update_extra_price",
                "dialog_size": "medium",
            },
        }

    def _without_no_variant_attributes(self) -> Self:
        return self.filtered(
            lambda pav: pav.attribute_id.create_variant != "no_variant",
        )

    def check_is_used_on_products(self):
        return self._in_use_message()
