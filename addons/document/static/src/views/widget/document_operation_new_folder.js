/** @odoo-module native */
import { UserFolder } from "@document/views/utils";
import { DESTINATION_MAX_LENGTH, truncate } from "@document/views/widget/utils";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs";
import { standardWidgetProps } from "@web/views/widgets";

export class DocumentsOperationNewFolder extends Component {
    static template = "document.DocumentsOperationNewFolder";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.documentService = useService("document.document");
    }

    async onClick() {
        const currentFolder = this.props.record.data.destination;
        const documents = this.props.record.data.document_ids.records.map((f) => ({
            id: f.resId,
            name: f.data.display_name,
        }));
        const attachmentId = this.props.record.data.attachment_id.id;
        const operation = this.props.record.data.operation;
        this.dialog.add(FormViewDialog, {
            canExpand: false,
            resModel: "document.document",
            size: "md",
            title: this.buttonLabel,
            context: {
                default_type: "folder",
                default_user_folder_id: currentFolder.toString(),
                ...(currentFolder === UserFolder.COMPANY
                    ? { default_access_internal: "edit" }
                    : {}),
                form_view_ref: "document.document_view_form_new_folder",
            },
            onRecordSaved: (result) => {
                this.documentService.openOperationDialog({
                    documents,
                    attachmentId,
                    operation,
                    context: {
                        default_destination: result.resId.toString(),
                        default_display_name: result.data.name,
                        default_user_permission: result.data.user_permission,
                    },
                });
            },
        });
    }

    get buttonLabel() {
        return _t("Create a folder in %(folder)s", {
            folder: truncate(
                this.props.record.data.display_name,
                DESTINATION_MAX_LENGTH,
            ),
        });
    }
}

export const documentsOperationNewFolder = {
    component: DocumentsOperationNewFolder,
    fieldDependencies: [
        { name: "attachment_id", type: "many2one" },
        { name: "destination", type: "char" },
        { name: "display_name", type: "char" },
        { name: "document_ids", type: "many2many" },
        { name: "operation", type: "char" },
    ],
};

registry
    .category("view_widgets")
    .add("documents_operation_new_folder", documentsOperationNewFolder);
