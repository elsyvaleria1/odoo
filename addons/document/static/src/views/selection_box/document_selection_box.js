/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { SelectionBox } from "@web/views/view_components";

export class DocumentsSelectionBox extends SelectionBox {
    setup() {
        super.setup();
        this.documentService = useService("document.document");
    }

    onUnselectAll() {
        super.onUnselectAll();
        this.documentService.bus.trigger("UPDATE-DOCUMENT-FOLDER");
    }
}
