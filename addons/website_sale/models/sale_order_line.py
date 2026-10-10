from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.website_sale.tools.shop_warning import acquire_shop_warning


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    name_short = fields.Char(compute="_compute_name_short")
    shop_warning = fields.Char(string="Warning")

    @api.depends("product_id.display_name")
    def _compute_name_short(self) -> None:
        for record in self:
            record.name_short = record.product_id.with_context(
                display_default_code=False
            ).display_name

    def get_description_following_lines(self):
        return reversed(self.name.splitlines()[1:])

    def _get_combination_name(self):
        return (
            self.product_id.product_template_attribute_value_ids._get_combination_name()
        )

    def _get_line_header(self):
        if not self.product_template_attribute_value_ids:
            return self.name_short
        return self.product_id.name

    def _get_date_order(self):
        self.check_singleton()
        if self.order_id.website_id and self.state == "draft":
            return fields.Datetime.now()
        return super()._get_date_order()

    def _acquire_shop_warning(self, clear: bool = True) -> str | None:
        return acquire_shop_warning(self, clear=clear)

    def _get_displayed_unit_price(self):
        show_tax = self.order_id.website_id.show_line_subtotals_tax_selection
        tax_display = (
            "total_excluded" if show_tax == "tax_excluded" else "total_included"
        )
        is_combo = self.product_type == "combo"
        unit_price = (
            self._get_price_display_regular_item() if is_combo else self.price_unit
        )

        return self.tax_ids.compute_all(
            unit_price,
            self.currency_id,
            1,
            self.product_id,
            self.partner_id,
        )[tax_display]

    def _prepare_reorder_cart_values(self, quantity) -> dict:
        self.check_singleton()
        return {
            "product_id": self.product_id.id,
            "product_template_id": self.product_id.product_tmpl_id.id,
            "quantity": quantity,
            "product_custom_attribute_values": self._get_custom_attribute_values_data(),
            "no_variant_attribute_value_ids": self.product_no_variant_attribute_value_ids.ids,
            "linked_products": self._prepare_reorder_combo_items(quantity),
        }

    def _get_custom_attribute_values_data(self) -> list[dict]:
        return [
            {
                "custom_product_template_attribute_value_id": pcav.custom_product_template_attribute_value_id.id,
                "custom_value": pcav.custom_value,
            }
            for pcav in self.product_custom_attribute_value_ids
        ]

    def _prepare_reorder_combo_items(self, quantity) -> list[dict]:
        # the combo as the configurator offers it today: per combo, the choice
        # made then if still offered, else the only one it holds, else none
        if self.product_id.type != "combo":
            return []
        chosen = {
            line.combo_item_id: line
            for line in self.linked_line_ids
            if line.combo_item_id
        }
        template = self.product_id.product_tmpl_id
        linked_products = []
        for combo in template.with_privilege(
            "website_sale.privilege_reorder_past_line",
            reason="a past combo comes back as the shop offers it today",
        ).combo_ids:
            item = next(
                (
                    item
                    for item in combo.combo_item_ids
                    if item.product_id.active
                    and (item in chosen or item._is_preselected())
                ),
                None,
            )
            if item:
                linked_products.append(
                    chosen.get(item, self.browse())._prepare_reorder_combo_item(
                        item, template, quantity
                    )
                )
        return linked_products

    def _prepare_reorder_combo_item(self, item, parent_template, quantity) -> dict:
        product = item.product_id
        selected_by_line = {}
        for ptav in (
            product.product_template_attribute_value_ids
            | self.product_no_variant_attribute_value_ids
            | product.attribute_line_ids.filtered(
                lambda ptal: not ptal._is_configurable()
            ).product_template_value_ids
        ):
            selected_by_line.setdefault(ptav.attribute_line_id, []).append(ptav)
        custom_values = {
            pcav.custom_product_template_attribute_value_id: pcav.custom_value
            for pcav in self.product_custom_attribute_value_ids
        }
        no_variant_ids = []
        custom_attribute_values = []
        for ptal in product.attribute_line_ids:
            selected = selected_by_line.get(ptal, [])
            if ptal.attribute_id.create_variant == "no_variant":
                no_variant_ids += [ptav.id for ptav in selected]
            custom = next((ptav for ptav in selected if custom_values.get(ptav)), None)
            if custom:
                custom_attribute_values.append(
                    {
                        "custom_product_template_attribute_value_id": custom.id,
                        "custom_value": custom_values[custom],
                    }
                )
        return {
            "product_template_id": product.product_tmpl_id.id,
            "parent_product_template_id": parent_template.id,
            "product_id": product.id,
            "quantity": quantity,
            "combo_item_id": item.id,
            "no_variant_attribute_value_ids": no_variant_ids,
            "product_custom_attribute_values": custom_attribute_values,
        }

    def _get_displayed_quantity(self):
        rounded_uom_qty = round(
            self.product_qty,
            self.env["decimal.precision"].get_precision("Product Unit"),
        )
        return (
            int(rounded_uom_qty) == rounded_uom_qty and int(rounded_uom_qty)
        ) or rounded_uom_qty

    def _show_in_cart(self):
        self.check_singleton()
        return (
            not self.is_delivery
            and not bool(self.display_type)
            and not bool(self.combo_item_id)
        )

    def _is_reorder_allowed(self) -> bool:
        self.check_singleton()
        return bool(
            bool(self.product_id)
            and self.product_id._is_add_to_cart_allowed()
            and self._show_in_cart()
        )

    def _get_cart_display_price(self):
        self.check_singleton()
        price_type = (
            "price_subtotal"
            if self.order_id.website_id.show_line_subtotals_tax_selection
            == "tax_excluded"
            else "price_total"
        )
        return sum(self._get_lines_with_price().mapped(price_type))

    def _is_zero_price_allowed(self) -> bool:
        return bool(
            self.combo_item_id
            or self.product_template_id.service_tracking
            in self.env["product.template"]._get_product_types_allow_zero_price()
        )

    def _check_validity(self):
        if (
            sum(self._get_lines_with_price().mapped("price_unit")) == 0
            and self.order_id.website_id.prevent_zero_price_sale
            and not self._is_zero_price_allowed()
        ):
            raise UserError(
                self.env._(
                    "The given product does not have a price therefore it cannot be added to cart.",
                )
            )

    def _is_strikethrough_price_shown(self) -> bool:
        return bool(
            self.discount and self._is_sellable() and self._get_displayed_unit_price()
        )

    def _is_sellable(self) -> bool:
        return bool(self.product_id.is_published and not self.is_delivery)
