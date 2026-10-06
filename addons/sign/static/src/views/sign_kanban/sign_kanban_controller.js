/** @odoo-module native */
import { useSignViewButtons } from "@sign/views/hooks";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban";

export class SignKanbanController extends KanbanController {
    static template = "sign.SignKanbanController";
    static components = {
        ...KanbanController.components,
        Dropdown,
        DropdownItem,
    };

    setup() {
        super.setup(...arguments);
        this.ui = useService("ui");
        this.uploadFileInputRef = elementRef();
        const functions = useSignViewButtons(this, this.uploadFileInputRef);
        Object.assign(this, functions);
    }
}
