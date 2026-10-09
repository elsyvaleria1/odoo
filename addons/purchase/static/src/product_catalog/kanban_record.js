/** @odoo-module native */
import {
    ProductCatalogKanbanRecord,
    productCatalogOrderLines,
} from "@product/product_catalog/kanban_record";

import { ProductCatalogPurchaseOrderLine } from "./purchase_order_line/purchase_order_line.js";

productCatalogOrderLines.add("purchase.order", ProductCatalogPurchaseOrderLine);

export class PurchaseProductCatalogKanbanRecord extends ProductCatalogKanbanRecord {}
