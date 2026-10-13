/** @odoo-module native */
import { t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";
import { SelectCreateDialog } from "@web/views/view_dialogs";

const log = makeLogger("document.add_documents");

export class SelectAddDocumentCreateDialog extends SelectCreateDialog {
    static template = "document.SelectAddDocumentCreateDialog";
    static props = {
        ...SelectCreateDialog.props,
        onAddAttachments: t.function().optional(),
        onPasteLinks: t.function(),
        attachTo: t.object().optional(),
        linksArePublic: t.boolean().optional(false),
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialogService = useService("dialog");
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
            const { resModel = "wizard.mail.message.send", resId = 0 } =
                this.props.attachTo || {};
            const attachmentRecords = await this.orm.call(
                "document.document",
                "add_documents_attachment",
                [resIds, resModel, resId],
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
            let links = await this.orm.read("document.document", resIds, [
                "display_name",
                "access_url",
                "access_via_link",
                "user_can_manage",
            ]);
            if (this.props.linksArePublic) {
                links = await this._shareForVisitors(links);
            }
            log.logic("pasteLinks", () => ({
                documents: resIds.length,
                pasted: links.length,
                linksArePublic: this.props.linksArePublic,
            }));
            if (!links.length) {
                return;
            }
            await this.props.onPasteLinks(links);
            this.notification.add(_t("Link(s) pasted!"), { type: "success" });
        });
    }

    /**
     * @param {Object[]} links
     * @returns {Promise<Object[]>}
     */
    async _shareForVisitors(links) {
        const isShared = (link) => link.access_via_link !== "none";
        const unshared = links.filter((link) => !isShared(link));
        const shareable = unshared.filter((link) => link.user_can_manage);
        const unshareable = unshared.filter((link) => !link.user_can_manage);
        log.logic("shareForVisitors", () => ({
            shared: links.length - unshared.length,
            shareable: shareable.map((link) => link.id),
            unshareable: unshareable.map((link) => link.id),
        }));
        if (unshareable.length) {
            this.notification.add(
                _t(
                    "Visitors could not open %s: it is not shared by link, and only who manages it can share it.",
                    unshareable.map((link) => link.display_name).join(", "),
                ),
                { type: "warning" },
            );
        }
        let shared = [];
        if (shareable.length && (await this._confirmSharing(shareable))) {
            await this.orm.call(
                "document.document",
                "action_update_access_rights",
                [shareable.map((link) => link.id)],
                { access_via_link: "view" },
            );
            shared = shareable;
        }
        const pasted = new Set([...links.filter(isShared), ...shared]);
        return links.filter((link) => pasted.has(link));
    }

    /**
     * @param {Object[]} links
     * @returns {Promise<boolean>}
     */
    _confirmSharing(links) {
        return new Promise((resolve) => {
            this.dialogService.add(
                ConfirmationDialog,
                {
                    title: _t("Share by link?"),
                    body: _t(
                        "Visitors can open only documents shared by link. Share %s so that anyone with the link can view it?",
                        links.map((link) => link.display_name).join(", "),
                    ),
                    confirmLabel: _t("Share and paste"),
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                },
                { onClose: () => resolve(false) },
            );
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
 * @param {{ add: Function }} dialog
 * @param {Object} props
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
