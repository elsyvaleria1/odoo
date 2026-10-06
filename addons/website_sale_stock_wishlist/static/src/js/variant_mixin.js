/** @odoo-module native */
import { renderToElement } from "@web/core/utils/render";
import VariantMixin from "@website_sale_stock/js/variant_mixin";

const oldChangeCombinationStock = VariantMixin._onChangeCombinationStock;
/**
 * @override
 */
VariantMixin._onChangeCombinationStock = function (ev, parent, combination) {
    oldChangeCombinationStock.apply(this, arguments);
    if (this.el.querySelector(".o_add_wishlist_dyn")) {
        const messageEl = this.el.querySelector("div.availability_messages");
        if (messageEl && !this.el.querySelector("#stock_wishlist_message")) {
            messageEl.append(
                renderToElement(
                    "website_sale_stock_wishlist.product_availability",
                    combination,
                ) || "",
            );
        }
    }
};
