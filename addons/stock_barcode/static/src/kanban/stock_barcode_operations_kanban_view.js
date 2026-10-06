/** @odoo-module native */
import { useBarcodeScreen } from "@stock_barcode/barcode_screen_hook";
import { registry } from "@web/core/registry";
import { KanbanController, kanbanView } from "@web/views/kanban";

// The operations kanban is a plain kanban but for one thing: it is a barcode
// screen, and the page has to know while it is on.
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
