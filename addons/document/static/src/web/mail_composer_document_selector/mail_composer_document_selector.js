/** @odoo-module native */
import { PASTE_SHARE_LINKS } from "@document/views/utils";
import { openDocumentsPicker } from "@document/views/view_dialogs/select_add_document_create_dialog";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useX2ManyCrud } from "@web/fields/relational/x2many_crud";
import { useViewModel } from "@web/model/model";
import { standardWidgetProps } from "@web/views/widgets";

export class MailComposerDocumentSelector extends Component {
    static template = "document.MailComposerDocumentSelector";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.model = useViewModel();
        this.dialogService = useService("dialog");
        this.operations = useX2ManyCrud(
            () => this.props.record.data["attachment_ids"],
            true,
        );
    }

    /** The wizard owns its attachment_ids: no chatter thread is involved. */
    addDocumentsAttachment = () => {
        openDocumentsPicker(this.dialogService, {
            onAddAttachments: (attachments) =>
                this.operations.linkRecords(attachments.map(({ id }) => id)),
            onPasteLinks: (links) =>
                this.model.bus.trigger(PASTE_SHARE_LINKS, { links }),
        });
    };
}

export const mailComposerDocumentSelector = {
    component: MailComposerDocumentSelector,
};

registry
    .category("view_widgets")
    .add("mail_composer_document_selector", mailComposerDocumentSelector);
