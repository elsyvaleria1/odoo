/** @odoo-module native */
import { AccountFileUploader } from "@account/components/account_file_uploader/account_file_uploader";
import { BankRecKanbanController } from "@account/components/bank_reconciliation/kanban_controller";
import {
    BankRecKanbanRenderer,
    BankRecKanbanView,
} from "@account/components/bank_reconciliation/kanban_renderer";
import { UploadDropZone } from "@account/components/upload_drop_zone/upload_drop_zone";
import { showUploadButton } from "@account_bank_statement_import/bank_reconciliation/upload_visibility";
import { proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useViewModel } from "@web/model/model";

export class BankRecKanbanUploadController extends BankRecKanbanController {
    static components = {
        ...BankRecKanbanController.components,
        AccountFileUploader,
    };

    get showUploadButton() {
        return showUploadButton(this.props.context);
    }
}

export class BankRecKanbanUploadRenderer extends BankRecKanbanRenderer {
    static components = {
        ...BankRecKanbanRenderer.components,
        UploadDropZone,
    };

    setup() {
        super.setup();
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

export const bankRecKanbanUploadView = {
    ...BankRecKanbanView,
    Controller: BankRecKanbanUploadController,
    Renderer: BankRecKanbanUploadRenderer,
    buttonTemplate: "account.BankRecoKanbanUploadButton",
};

registry
    .category("views")
    .add("bank_rec_widget_kanban", bankRecKanbanUploadView, { force: true });
