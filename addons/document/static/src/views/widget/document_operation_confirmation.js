/** @odoo-module native */
import { DESTINATION_MAX_LENGTH, truncate } from "@document/views/widget/utils";
import { Component, proxy, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

const log = makeLogger("document.operation");

export class DocumentsOperationConfirmation extends Component {
    static template = "document.DocumentsOperationConfirmation";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.documentService = useService("document.document");
        this.state = proxy({ pending: false });
    }

    get buttonLabel() {
        const destination = {
            folder_name: truncate(
                this.props.record.data.display_name,
                DESTINATION_MAX_LENGTH,
            ),
        };
        if (this.props.record.data.user_permission !== "edit") {
            return _t("Insufficient access to %(folder_name)s", destination);
        }
        if (this.props.record.data.operation === "shortcut") {
            if (this.isMultiDocuments) {
                return _t("Create shortcuts in %(folder_name)s", destination);
            }
            return _t("Create a shortcut in %(folder_name)s", destination);
        } else if (this.props.record.data.operation === "add") {
            return _t("Add in %(folder_name)s", destination);
        } else if (this.props.record.data.operation === "copy") {
            return _t("Duplicate in %(folder_name)s", destination);
        } else if (this.props.record.data.operation === "move") {
            return _t("Move to %(folder_name)s", destination);
        }
        return _t("Confirm");
    }

    async onClick() {
        if (this.state.pending) {
            return;
        }
        this.state.pending = true;
        try {
            await this.confirm();
        } finally {
            this.state.pending = false;
        }
    }

    async confirm() {
        log.logic("confirm", () => ({
            operation: this.props.record.data.operation,
            destination: this.props.record.data.destination,
            documents: this.props.record.data.document_ids.records.length,
            dirty: this.props.record.dirty,
        }));
        // unconditionally: a destination changed after a cancelled warning
        // lives only in the record until saved, a clean record saves nothing
        if (!(await this.props.record.save())) {
            return;
        }
        // a move changing access is refused and reported, then made once accepted
        const confirmed = await this.documentService.moveConfirmingAccess(
            (context) =>
                this.orm.call(
                    "wizard.document.document.place.folder",
                    "action_confirm",
                    [this.props.record.resId],
                    { context },
                ),
            this.props.record.data.display_name,
        );
        if (!confirmed) {
            log.logic("access warning declined");
            return;
        }
        this.notifySuccess();
        this.dialogContext.dialogData.close();
    }

    notifySuccess() {
        const destination = { folder_name: this.props.record.data.display_name };
        let message = "";
        if (this.props.record.data.operation === "shortcut") {
            if (this.isMultiDocuments) {
                message = _t("Shortcuts created in %(folder_name)s!", destination);
            } else {
                message = _t("Shortcut created in %(folder_name)s!", destination);
            }
        } else if (this.props.record.data.operation === "move") {
            if (this.isMultiDocuments) {
                message = _t("Documents moved to %(folder_name)s!", destination);
            } else {
                message = _t("Document moved to %(folder_name)s!", destination);
            }
        } else if (["add", "copy"].includes(this.props.record.data.operation)) {
            if (this.isMultiDocuments) {
                message = _t("Documents created in %(folder_name)s!", destination);
            } else {
                message = _t("Document created in %(folder_name)s!", destination);
            }
        }
        this.notification.add(message, { title: _t("Done"), type: "success" });
    }

    get isMultiDocuments() {
        return this.props.record.data.document_ids.records.length > 1;
    }
}

export const documentsOperationConfirmation = {
    component: DocumentsOperationConfirmation,
    fieldDependencies: [
        { name: "display_name", type: "char" },
        { name: "destination", type: "char" },
        { name: "document_ids", type: "many2many" },
        { name: "operation", type: "char" },
    ],
};

registry
    .category("view_widgets")
    .add("documents_operation_confirmation", documentsOperationConfirmation);
