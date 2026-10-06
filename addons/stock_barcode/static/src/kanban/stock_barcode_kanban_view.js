/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { StockBarcodeKanbanController } from "./stock_barcode_kanban_controller.js";
import { StockBarcodeKanbanRenderer } from "./stock_barcode_kanban_renderer.js";

export const stockBarcodeKanbanView = Object.assign({}, kanbanView, {
    Controller: StockBarcodeKanbanController,
    Renderer: StockBarcodeKanbanRenderer,
});
registry.category("views").add("stock_barcode_list_kanban", stockBarcodeKanbanView);
