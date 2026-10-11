/** @odoo-module native */
import { documentActions, documentActionText } from "@document/views/document_actions";
import { useDocumentContext } from "@document/views/document_context";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useViewModel } from "@web/model/model";
import { standardWidgetProps } from "@web/views/widgets";

export class DocumentsListActionWidget extends Component {
    static props = { ...standardWidgetProps };
    static template = "document.DocumentsListActionWidget";
    static actionIds = ["share", "download", "rename", "details", "open"];
    props = useProps(this.constructor.props);

    setup() {
        this.config = useViewConfig();
        this.model = useViewModel();
        this.documentContext = useDocumentContext();
        this.documentService = useService("document.document");
    }

    get visibleActions() {
        const data = this.props.record.data;
        return this.constructor.actionIds
            .map((id) => ({ id, action: documentActions[id] }))
            .filter(({ action }) => action.isVisible(this.documentService, data))
            .map(({ id, action }) => ({
                id,
                action,
                icon: documentActionText(action, "icon", data),
                label: documentActionText(action, "label", data),
            }));
    }

    run(action) {
        return action.run(
            {
                documentService: this.documentService,
                model: this.model,
                reload: () =>
                    this.props.record.data.type === "folder"
                        ? this.model._notifyChange()
                        : this.props.record.load(),
                bus: this.documentContext.documentsView.bus,
                record: this.props.record,
            },
            this.props.record.data,
        );
    }
}

export const documentsListActionWidget = {
    component: DocumentsListActionWidget,
};

registry
    .category("view_widgets")
    .add("documents_list_actions", documentsListActionWidget);
