/** @odoo-module native */
import { ProductProduct } from "@sale/js/models/product_product";
import { patch } from "@web/core/utils/patch";

patch(ProductProduct.prototype, {
    /**
     * @param {number} qty_free
     * @param args
     */
    setup({ qty_free, ...args }) {
        super.setup(args);
        this.qty_free = qty_free;
    },

    /**
     * @param {Number} quantity
     * @return {Boolean}
     */
    isQuantityAllowed(quantity) {
        return this.qty_free === undefined || this.qty_free >= quantity;
    },
});
