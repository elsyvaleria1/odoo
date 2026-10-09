/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import wishlistUtils from "@website_sale_wishlist/js/website_sale_wishlist_utils";

/**
 * Follows `website_sale_wishlist:product_added`, which a route that puts a
 * product on the wishlist sends with its fragments: the wishlist this tab
 * remembers and the header's count.
 */
export class WishlistUpdates extends Interaction {
    static selector = "#wrapwrap";
    dynamicContent = {
        _document: {
            "t-on-website_sale_wishlist:product_added.noUpdate": (ev) => {
                wishlistUtils.addWishlistProduct(ev.detail.product_id);
                wishlistUtils.updateWishlistNavBar();
            },
        },
    };
}

registry
    .category("public.interactions")
    .add("website_sale_wishlist.wishlist_updates", WishlistUpdates);
