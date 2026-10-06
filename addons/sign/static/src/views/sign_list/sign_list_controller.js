/** @odoo-module native */
import { SignActionHelper } from "@sign/views/helper/sign_action_helper";
import { useSignViewButtons } from "@sign/views/hooks";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { useDebugMode } from "@web/core/debug/debug_context";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { ListController, ListRenderer } from "@web/views/list";

import { SignDocumentDropZone } from "../../mixin/document_upload.js";

export class SignListController extends ListController {
    static template = "sign.SignListController";
    static components = {
        ...ListController.components,
        Dropdown,
        DropdownItem,
    };

    setup() {
        super.setup(...arguments);
        this.dialogContext = useDialogContext();
        this.ui = useService("ui");
        this.uploadFileInputRef = elementRef();
        const functions = useSignViewButtons(this, this.uploadFileInputRef);
        Object.assign(this, functions);
    }
}

export class SignListRenderer extends SignDocumentDropZone(ListRenderer) {
    static template = "sign.ListRenderer";
    static components = {
        ...ListRenderer.components,
        SignActionHelper,
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }
}
