/** @odoo-module native */
import { useBarcodeScreen } from "@stock_barcode/barcode_screen_hook";
import { registry } from "@web/core/registry";
import { KanbanController, kanbanView } from "@web/views/kanban";

export class StockBarcodeOperationsKanbanController extends KanbanController {
    setup() {
        super.setup(...arguments);
        useBarcodeScreen("kanban");
    }
}

export const stockBarcodeOperationsKanbanView = Object.assign({}, kanbanView, {
    Controller: StockBarcodeOperationsKanbanController,
});
registry
    .category("views")
    .add("stock_barcode_operations_kanban", stockBarcodeOperationsKanbanView);
