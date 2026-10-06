/** @odoo-module native */
import { t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";
import { SelectCreateDialog } from "@web/views/view_dialogs";

const log = makeLogger("document.add_documents");

/**
 * Picks documents to attach, or to paste as links. What happens to them is
 * the caller's: a chatter composer, a mail wizard, an HTML field.
 */
export class SelectAddDocumentCreateDialog extends SelectCreateDialog {
    static template = "document.SelectAddDocumentCreateDialog";
    static props = {
        ...SelectCreateDialog.props,
        /** absent where nothing can be attached yet (an unsaved record) */
        onAddAttachments: t.function().optional(),
        onPasteLinks: t.function(),
        /** where the attachment copies are made: resModel, resId, isPublic */
        attachTo: t.object().optional(),
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get viewProps() {
        const baseProps = super.viewProps;
        return {
            ...omit(baseProps, "forceGlobalClick", "display"),
            type: "list",
            allowSelectors: true,
        };
    }

    /**
     * Runs once whatever the clicks (a double click, the hotkey twice would
     * copy the attachments twice), then closes; a failure is told, not thrown.
     *
     * @param {string} failurePrefix
     * @param {() => Promise<void>} callback
     */
    _runOnceAndClose(failurePrefix, callback) {
        return this.executeOnceAndClose(async () => {
            try {
                await callback();
            } catch (error) {
                this._notifyFailure(failurePrefix, error);
            }
        });
    }

    /** @param {number[]} resIds */
    addAttachments(resIds) {
        return this._runOnceAndClose(_t("Failed to add document(s): "), async () => {
            const {
                resModel = "wizard.mail.message.send",
                resId = 0,
                isPublic = false,
            } = this.props.attachTo || {};
            const attachmentRecords = await this.orm.call(
                "document.document",
                "add_documents_attachment",
                [resIds, resModel, resId, isPublic],
            );
            const attachments = await this._processAttachments(attachmentRecords);
            log.logic("addAttachments", () => ({
                documents: resIds.length,
                attachments: attachments.length,
                resModel,
            }));
            await this.props.onAddAttachments(attachments);
        });
    }

    /** @param {number[]} resIds */
    pasteLinks(resIds) {
        return this._runOnceAndClose(_t("Failed to paste link(s): "), async () => {
            const links = await this.orm.read("document.document", resIds, [
                "display_name",
                "access_url",
            ]);
            await this.props.onPasteLinks(links);
            this.notification.add(_t("Link(s) pasted!"), { type: "success" });
        });
    }

    /**
     * @param {Object[]} attachmentRecords
     * @returns {Promise<Object[]>}
     */
    async _processAttachments(attachmentRecords) {
        return attachmentRecords;
    }

    _notifyFailure(prefix, error) {
        this.notification.add(prefix + (error.data?.message || error.toString()), {
            type: "danger",
        });
    }
}

/**
 * The documents a composer or an editor can attach or link: files only, and
 * never the trash.
 *
 * @param {{ add: Function }} dialog the dialog service, or an editor's
 *      adapter over its own dialogs
 * @param {Object} props onAddAttachments, onPasteLinks, attachTo
 */
export function openDocumentsPicker(dialog, props) {
    return dialog.add(SelectAddDocumentCreateDialog, {
        resModel: "document.document",
        title: _t("Search: Documents"),
        noCreate: true,
        domain: [
            ["type", "=", "binary"],
            ["shortcut_document_id", "=", false],
        ],
        context: {
            list_view_ref: "document.documents_view_list_add_documents_attachment",
            documents_search_panel_no_trash: true,
            documents_view_secondary: true,
        },
        ...props,
    });
}
