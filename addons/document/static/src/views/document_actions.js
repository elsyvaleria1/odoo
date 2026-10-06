/** @odoo-module native */
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";

/**
 * Mirrors `document.document._locked_by_other`: a lock stops everyone but the
 * user who took it, and a Documents manager.
 *
 * @param {Object} data a `document.document` read
 * @param {boolean} userIsDocumentManager
 * @returns {boolean}
 */
export function isLockedByOther(data, userIsDocumentManager) {
    return (
        !userIsDocumentManager &&
        Boolean(data.lock_uid) &&
        data.lock_uid.id !== user.userId
    );
}

/**
 * Mirrors what `document.document.action_archive` accepts: an active document
 * the user may edit, not under another user's lock, and either theirs or in a
 * folder they may edit. A folder the caller cannot tell is the server's to judge.
 *
 * @param {Object} data a `document.document` read
 * @param {Object} params
 * @param {boolean} params.userIsDocumentManager
 * @param {(folderId: number) => string|undefined} params.folderPermission
 * @returns {boolean}
 */
export function isTrashable(data, { userIsDocumentManager, folderPermission }) {
    if (
        data.active === false ||
        data.user_permission !== "edit" ||
        isLockedByOther(data, userIsDocumentManager)
    ) {
        return false;
    }
    const folderId = data.folder_id?.id;
    if (data.owner_id?.id === user.userId || !folderId) {
        return true;
    }
    return (folderPermission(folderId) ?? "edit") === "edit";
}

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
            data.active !== false && documentService.isEditable(data),
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
        run: async ({ documentService, reload }, data) => {
            await documentService.toggleFavorite([data.id]);
            await reload();
        },
    },
    trash: {
        icon: "fa-regular fa-trash-can",
        label: _t("Move to Trash"),
        isVisible: (documentService, data) =>
            documentService.userIsInternal &&
            data.active !== false &&
            !isLockedByOther(data, documentService.userIsDocumentManager) &&
            documentService.isEditable(data),
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
            bus.trigger("documents-open-automations", {
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
