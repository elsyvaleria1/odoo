/** @odoo-module native */
import { openDocumentsPicker } from "@document/views/view_dialogs/select_add_document_create_dialog";
import { renderStaticFileBox } from "@html_editor/main/media/media_dialog/document_selector";
import { Plugin } from "@html_editor/plugin";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { _t } from "@web/core/translation";

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
        const { resModel, resId: rawResId } = this.config.getRecordInfo?.() || {};
        // a view's content is served to website visitors: they get links to
        // the documents, shared by link, never copies outside their access
        const isPublic = resModel === "ir.ui.view";
        const resId = parseInt(rawResId) || false;
        const dialog = {
            add: (...args) => this.dependencies.dialog.addDialog(...args),
        };
        openDocumentsPicker(dialog, {
            // an unsaved record has nothing to attach the copies to yet
            onAddAttachments:
                resId && !isPublic
                    ? (attachments) => this.insertFiles(attachments)
                    : undefined,
            attachTo: { resModel, resId },
            linksArePublic: isPublic,
            onPasteLinks: (links) => this.insertLinks(links),
        });
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
