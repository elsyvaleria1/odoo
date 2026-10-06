/** @odoo-module native */
import { t } from "@odoo/owl";
import { ProductCard, productCardProps } from "@sale/js/product_card/product_card";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

Object.assign(productCardProps, {
    quantity: t.number().optional(),
});

patch(ProductCard.prototype, {
    setup() {
        super.setup(...arguments);
        this.allQuantitySelectedTooltip = _t("All available quantity selected");
    },
});
