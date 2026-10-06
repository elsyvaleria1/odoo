/** @odoo-module native */
import { AccountFileUploader } from "@account/components/account_file_uploader/account_file_uploader";
import {
    BankRecListController,
    BankRecListRenderer,
    bankRecListView,
} from "@account/components/bank_reconciliation/list_view/list";
import { UploadDropZone } from "@account/components/upload_drop_zone/upload_drop_zone";
import { showUploadButton } from "@account_bank_statement_import/bank_reconciliation/upload_visibility";
import { proxy } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { useViewModel } from "@web/model/model";
import { ListRenderer } from "@web/views/list";

export class BankRecListUploadController extends BankRecListController {
    static components = {
        ...BankRecListController.components,
        AccountFileUploader,
    };

    get showUploadButton() {
        return showUploadButton(this.props.context);
    }
}

export class BankRecListUploadRenderer extends BankRecListRenderer {
    static template = "account.BankRecListUploadRenderer";
    static components = {
        ...ListRenderer.components,
        UploadDropZone,
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.model = useViewModel();
        this.dropzoneState = proxy({ visible: false });
    }

    onDragStart(ev) {
        if (ev.dataTransfer.types.includes("Files")) {
            this.dropzoneState.visible = true;
        }
    }

    get showUploadButton() {
        return showUploadButton(this.model.config.context);
    }
}

export const bankRecListUploadView = {
    ...bankRecListView,
    Controller: BankRecListUploadController,
    Renderer: BankRecListUploadRenderer,
    buttonTemplate: "account.BankRecListUploadButtons",
};

registry.category("views").add("bank_rec_list", bankRecListUploadView, { force: true });
