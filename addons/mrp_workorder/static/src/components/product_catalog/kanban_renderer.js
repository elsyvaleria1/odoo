/** @odoo-module native */

import { t } from "@odoo/owl";
import { productCatalogKanbanRendererProps } from "@product/product_catalog/kanban_renderer";

productCatalogKanbanRendererProps.pushCatalogKanbanUpdate = t.any().optional();
