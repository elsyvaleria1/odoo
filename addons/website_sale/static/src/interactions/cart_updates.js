/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import wSaleUtils from "@website_sale/js/website_sale_utils";

export class CartUpdates extends Interaction {
    static selector = "#wrapwrap";
    dynamicContent = {
        _document: {
            "t-on-website_sale:cart_updated.noUpdate": (ev) =>
                this.onCartUpdated(ev.detail),
        },
    };

    /**
     * @param {{ cart_quantity: number, cart_ready: boolean, warning: string, quick_reorder: boolean }} cart
     */
    onCartUpdated(cart) {
        wSaleUtils.updateCartNavBar(cart);
        wSaleUtils.showWarning(cart.warning);
        if (cart.quick_reorder && document.getElementById("quick_reorder_button")) {
            wSaleUtils.updateQuickReorderButton();
        }
    }
}

registry.category("public.interactions").add("website_sale.cart_updates", CartUpdates);
