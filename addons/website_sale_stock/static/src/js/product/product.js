/** @odoo-module native */
import { t } from "@odoo/owl";
import { Product, productProps } from "@sale/js/product/product";
import { patch } from "@web/core/utils/patch";
import { useWebsiteSaleStockContext } from "@website_sale_stock/js/product_configurator_dialog/website_sale_stock_context";

Object.assign(productProps, {
    qty_free: t.number().optional(),
});

patch(Product.prototype, {
    setup() {
        super.setup(...arguments);
        this.websiteSaleStockContext = useWebsiteSaleStockContext();
    },

    /**
     * @return {Boolean}
     */
    isOutOfStock() {
        return !this.websiteSaleStockContext.isQuantityAllowed(this.props, 1);
    },
});
