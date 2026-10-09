/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import wishlistUtils from "@website_sale_wishlist/js/website_sale_wishlist_utils";

/**
 * The wishlist page. Removing an item is its own post form, answered by the
 * page, swapped in place; this keeps the wishlist the tab remembers and the
 * header's count in step with what the server rendered, and puts a product
 * in the cart before removing it.
 */
export class ProductWishlist extends Interaction {
    static selector = ".wishlist-section";
    dynamicContent = {
        ".o_wish_add": { "t-on-click": this.addToCart },
    };

    start() {
        wishlistUtils.setWishlistProductIds(
            JSON.parse(this.el.dataset.wishlistProductIds || "[]"),
        );
        wishlistUtils.updateWishlistNavBar();
    }

    /**
     * @param {Event} ev
     */
    async addToCart(ev) {
        const button = /** @type {HTMLElement} */ (ev.currentTarget);
        const quantity = await this.waitFor(
            this.services["cart"].add(
                {
                    productTemplateId: parseInt(button.dataset.productTemplateId),
                    productId: parseInt(button.dataset.productProductId),
                    isCombo: button.dataset.productType === "combo",
                    ptavs: JSON.parse(button.dataset.ptavIds || "[]"),
                },
                {
                    isConfigured: false,
                    redirectToCart: false,
                    showQuantity: Boolean(button.dataset.showQuantity),
                },
            ),
        );
        if (quantity > 0) {
            // the item leaves the wishlist; the last one leads to the cart
            const form = /** @type {HTMLFormElement} */ (
                button.closest("article").querySelector("form[action*='/remove/']")
            );
            form.elements.namedItem("empty_redirect").value = "/shop/cart";
            form.requestSubmit();
        }
    }
}

registry
    .category("public.interactions")
    .add("website_sale_wishlist.product_wishlist", ProductWishlist);
