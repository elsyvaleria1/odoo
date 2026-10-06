/** @odoo-module native */
import { useFsmContext } from "@industry_fsm_sale/fsm_context";
import { t } from "@odoo/owl";
import { ProductCatalogOrderLine } from "@product/product_catalog/order_line/order_line";
import {
    ProductCatalogSaleOrderLine,
    productCatalogSaleOrderLineProps,
} from "@sale_stock/product_catalog/sale_order_line/sale_order_line";
import { patch } from "@web/core/utils/patch";

Object.assign(productCatalogSaleOrderLineProps, {
    tracking: t.boolean(),
    minimumQuantityOnProduct: t.number(),
});

patch(ProductCatalogOrderLine.prototype, {
    setup() {
        super.setup(...arguments);
        this.fsmContext = useFsmContext();
    },
});

patch(ProductCatalogSaleOrderLine.prototype, {
    get disableRemove() {
        if (this.fsmContext.fsm_task_id) {
            return this.props.quantity === this.props.minimumQuantityOnProduct;
        }
        return this.props.quantity === this.props.deliveredQty;
    },
});
