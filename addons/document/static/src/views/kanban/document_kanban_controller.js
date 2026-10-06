/** @odoo-module native */
import { DocumentsCogMenu } from "@document/views/cog_menu/document_cog_menu";
import { DocumentsControllerMixin } from "@document/views/document_controller_mixin";
import { DocumentsSelectionBox } from "@document/views/selection_box/document_selection_box";
import { Dropdown } from "@web/components/dropdown";
import { KanbanController } from "@web/views/kanban";

export class DocumentsKanbanController extends DocumentsControllerMixin(
    KanbanController,
) {
    static template = "document.DocumentsKanbanView";
    static components = {
        ...KanbanController.components,
        Dropdown,
        DocumentsCogMenu,
        SelectionBox: DocumentsSelectionBox,
    };
}
