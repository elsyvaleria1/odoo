/** @odoo-module native */
import { t } from "@odoo/owl";
import { productCatalogOrderLineProps } from "@product/product_catalog/order_line/order_line";

Object.assign(productCatalogOrderLineProps, {
    plan_name: t.string().optional(),
});
