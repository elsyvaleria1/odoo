/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { PurchaseOrderLineCompareListRenderer } from "./purchase_order_line_compare_list_renderer.js";

export const PurchaseOrderLineCompareListView = {
    ...listView,
    Renderer: PurchaseOrderLineCompareListRenderer,
};

registry
    .category("views")
    .add("purchase_order_line_compare", PurchaseOrderLineCompareListView);
