/** @odoo-module native */
import { DocumentsViewEvent } from "@document/views/utils";
import { _t } from "@web/core/translation";

/**
 * Mirrors `document.document._is_download_allowed`: a blocked document is still
 * downloaded by whoever may edit it. A shortcut answers for its target, which
 * is not loaded here, so the server decides.
 *
 * @param {Object} data a `document.document` read
 * @returns {boolean}
 */
export function isDownloadAllowed(data) {
    return (
        Boolean(data.shortcut_document_id) ||
        !data.is_download_blocked ||
        data.user_permission === "edit" ||
        data.access_via_link === "edit"
    );
}

/**
 * @typedef {Object} DocumentActionContext
 * @property {import("@document/core/document_service").DocumentService} documentService
 * @property {Object} model the documents view's model
 * @property {() => Promise<void>} reload reloads what the action changed
 * @property {import("@odoo/owl").EventBus} bus the documents view's bus
 * @property {Object} [record] the row's record, on a list row only
 */

/**
 * @typedef {Object} DocumentAction
 * @property {string | ((data: Object) => string)} icon
 * @property {string | ((data: Object) => string)} label
 * @property {(documentService: Object, data: Object) => boolean} isVisible
 * @property {(context: DocumentActionContext, data: Object) => any} run
 */

/** A document or a folder of the tree, not one of its special roots (MY, COMPANY…). */
const isRealDocument = (data) => typeof data?.id === "number";

/**
 * What can be done on one document or folder, answered once for every surface
 * showing it: the cog menu (on the current folder, a search-panel value) and a
 * list row (on its record's data). Each surface picks the entries it offers.
 *
 * @type {Record<string, DocumentAction>}
 */
export const documentActions = {
    share: {
        icon: "fa-solid fa-share-nodes",
        label: _t("Share…"),
        isVisible: (documentService, data) =>
            documentService.userIsInternal &&
            data.active !== false &&
            !data.is_locked_by_other &&
            isRealDocument(data),
        run: ({ documentService }, data) =>
            documentService.openSharingDialog([data.id]),
    },
    download: {
        icon: "fa-solid fa-download",
        label: _t("Download"),
        isVisible: (documentService, data) =>
            isRealDocument(data) &&
            (data.type !== "binary" || Boolean(data.attachment_id)) &&
            isDownloadAllowed(data),
        run: ({ documentService }, data) => documentService.downloadDocument(data),
    },
    rename: {
        icon: "fa-solid fa-pen-to-square",
        label: _t("Rename…"),
        isVisible: (documentService, data) =>
            data.active !== false &&
            !data.is_locked_by_other &&
            documentService.isEditable(data),
        run: async ({ documentService, reload }, data) => {
            if (await documentService.openDialogRename(data.id)) {
                await reload();
            }
        },
    },
    details: {
        icon: "fa-solid fa-circle-info",
        label: _t("Info & Tags"),
        isVisible: (documentService, data) =>
            documentService.userIsInternal && isRealDocument(data),
        run: ({ documentService, record }) => {
            // a row shows its own details; the cog, the focused folder's
            if (record && documentService.focusedRecord?.id !== record.id) {
                documentService.focusRecord(record);
                if (!documentService.rightPanelReactive.visible) {
                    documentService.toggleRightPanelVisibility();
                }
                return;
            }
            documentService.toggleRightPanelVisibility();
        },
    },
    open: {
        icon: "fa-solid fa-right-to-bracket",
        label: _t("Go inside"),
        isVisible: (documentService, data) => data.type === "folder",
        run: ({ record }) => record.openFolder(),
    },
    shortcut: {
        icon: "fa-solid fa-up-right-from-square",
        label: _t("Add Shortcut…"),
        isVisible: (documentService, data) =>
            documentService.isEditable(data) &&
            !data.shortcut_document_id &&
            typeof data.user_folder_id === "number",
        run: ({ documentService, reload }, data) =>
            documentService.openOperationDialog({
                documents: [{ id: data.id, name: data.display_name }],
                operation: "shortcut",
                onClose: () => reload(),
            }),
    },
    star: {
        icon: (data) =>
            data.is_user_favorite ? "fa-solid fa-star" : "fa-regular fa-star",
        label: (data) => (data.is_user_favorite ? _t("Remove Star") : _t("Add Star")),
        // a star is the user's own, not a change to the document: reading it is enough
        isVisible: (documentService, data) =>
            isRealDocument(data) && data.active !== false,
        run: ({ model }, data) => model.toggleFavorite([data.id]),
    },
    trash: {
        icon: "fa-regular fa-trash-can",
        label: _t("Move to Trash"),
        // the server's answer (user_can_trash): what action_archive accepts
        isVisible: (documentService, data) =>
            documentService.userIsInternal &&
            documentService.isEditable(data) &&
            Boolean(data.user_can_trash),
        run: async ({ documentService, reload }, data) => {
            if (await documentService.moveToTrash([data.id])) {
                await reload();
            }
        },
    },
    automations: {
        icon: "fa-solid fa-robot",
        label: _t("Automations…"),
        isVisible: (documentService, data) =>
            documentService.userIsDocumentUser && documentService.isEditable(data),
        run: ({ bus }, data) =>
            bus.trigger(DocumentsViewEvent.OPEN_AUTOMATIONS, {
                folderId: data.id,
                folderDisplayName: data.display_name,
            }),
    },
};

/**
 * @param {DocumentAction} action
 * @param {"icon"|"label"} key
 * @param {Object} data
 * @returns {string}
 */
export function documentActionText(action, key, data) {
    const value = action[key];
    return typeof value === "function" ? value(data) : value;
}
