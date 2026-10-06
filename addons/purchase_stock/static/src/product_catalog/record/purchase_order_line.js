/** @odoo-module native */
import { t } from "@odoo/owl";
import { ProductCatalogPurchaseOrderLine } from "@purchase/product_catalog/purchase_order_line/purchase_order_line";

export class ProductCatalogPurchaseSuggestOrderLine extends ProductCatalogPurchaseOrderLine {
    static props = {
        ...ProductCatalogPurchaseOrderLine.props,
        suggested_qty: t.number().optional(),
    };
}
