/** @odoo-module native */
import { openDocumentsPicker } from "@document/views/view_dialogs/select_add_document_create_dialog";
import { renderStaticFileBox } from "@html_editor/main/media/media_dialog/document_selector";
import { Plugin } from "@html_editor/plugin";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";

const log = makeLogger("document.editor");

export class AddDocumentsAttachmentPlugin extends Plugin {
    static id = "add_documents_attachment";
    static dependencies = ["dom", "history", "dialog", "link"];
    resources = {
        user_commands: {
            id: "addDocumentsAttachment",
            title: _t("File"),
            description: _t("Insert a file from Documents"),
            icon: "o_add_documents_icon",
            run: this.openSelectAddDocumentCreateDialog.bind(this),
        },
        powerbox_items: {
            categoryId: "media",
            commandId: "addDocumentsAttachment",
            keywords: [_t("file"), _t("document")],
        },
    };

    openSelectAddDocumentCreateDialog() {
        const dialog = {
            add: (...args) => this.dependencies.dialog.addDialog(...args),
        };
        openDocumentsPicker(dialog, this.documentsPickerProps());
    }

    /** @returns {Object} */
    documentsPickerProps() {
        const { resModel, resId: rawResId } = this.config.getRecordInfo?.() || {};
        const linksArePublic = Boolean(this.config.publicAttachments);
        const resId = parseInt(rawResId) || false;
        log.logic("documentsPickerProps", () => ({ resModel, resId, linksArePublic }));
        return {
            onAddAttachments:
                resId && !linksArePublic
                    ? (attachments) => this.insertFiles(attachments)
                    : undefined,
            attachTo: { resModel, resId },
            linksArePublic,
            onPasteLinks: (links) => this.insertLinks(links),
        };
    }

    /** @param {Object[]} attachments */
    insertFiles(attachments) {
        if (this.config.onAttachmentChange) {
            attachments.forEach(this.config.onAttachmentChange);
        }
        attachments
            .map((attachment) => this.renderDownloadBox(attachment))
            .forEach(this.dependencies.dom.insert);
        this.dependencies.history.addStep();
        this.services.notification.add(_t("Document(s) added!"), { type: "success" });
    }

    /** @param {Object[]} links */
    insertLinks(links) {
        for (const { display_name, access_url } of links) {
            this.dependencies.link.insertLink(access_url, display_name);
            this.dependencies.dom.insert(" ");
        }
    }

    renderDownloadBox(attachment) {
        const url = this.services.uploadLocalFiles.getURL(attachment, {
            download: true,
            unique: true,
            accessToken: true,
        });
        const { name: filename, mimetype, id } = attachment;
        return renderStaticFileBox(filename, mimetype, url, id);
    }
}

MAIN_PLUGINS.push(AddDocumentsAttachmentPlugin);
