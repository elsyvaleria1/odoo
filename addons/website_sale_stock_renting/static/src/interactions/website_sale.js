/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { patchDynamicContent } from "@web/public/utils";
import { WebsiteSale } from "@website_sale/interactions/website_sale";

patch(WebsiteSale.prototype, {
    setup() {
        super.setup();
        patchDynamicContent(this.dynamicContent, {
            'input[type="hidden"][name="product_id"]': {
                "t-on-change": this.onVariantChanged.bind(this),
            },
        });
    },

    /**
     * @override
     * @private
     * @returns {void}
     */
    _updateRootProduct() {
        super._updateRootProduct(...arguments);
        const dateRangeRenting = this.el.querySelector(
            ".o_website_sale_daterange_picker",
        );
        dateRangeRenting?.dispatchEvent(
            new CustomEvent("change_product_id", {
                detail: { productId: this.rootProduct.productId },
            }),
        );
    },

    /**
     * @override
     */
    onVariantChanged() {
        const productIdElement = this.el.querySelector(
            'input[type="hidden"][name="product_id"]',
        );
        const dateRangeRenting = this.el.querySelector(
            ".o_website_sale_daterange_picker",
        );
        if (dateRangeRenting && productIdElement) {
            dateRangeRenting.dispatchEvent(
                new CustomEvent("change_product_id", {
                    detail: { productId: parseInt(productIdElement.value) },
                }),
            );
        }
    },

    /**
     * @override
     */
    onRentingConstraintsChanged(event) {
        super.onRentingConstraintsChanged(...arguments);
        const info = event.detail;
        if (info.preparationTime !== undefined) {
            this.preparationTime = info.preparationTime;
        }
    },
});
