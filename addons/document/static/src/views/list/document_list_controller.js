/** @odoo-module native */
import { DocumentsCogMenu } from "@document/views/cog_menu/document_cog_menu";
import { DocumentsControllerMixin } from "@document/views/document_controller_mixin";
import { DocumentsSelectionBox } from "@document/views/selection_box/document_selection_box";
import { Dropdown } from "@web/components/dropdown";
import { ListController } from "@web/views/list";

export class DocumentsListController extends DocumentsControllerMixin(ListController) {
    static template = "document.DocumentsListController";
    static components = {
        ...ListController.components,
        Dropdown,
        DocumentsCogMenu,
        SelectionBox: DocumentsSelectionBox,
    };

    setup() {
        super.setup(...arguments);
        if (!this.documentService.userIsInternal) {
            this.archInfo = {
                ...this.archInfo,
                columns: this.archInfo.columns.filter(
                    (col) => !this.internalOnlyColumns.includes(col.name),
                ),
            };
        }
    }

    get internalOnlyColumns() {
        return ["company_id"];
    }
}
