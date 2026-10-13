/** @odoo-module native */
import { markup } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { htmlJoin } from "@web/core/utils/dom/html";
/** @typedef {typeof import("@web/model/relational_model/record").RelationalRecord} RelationalModelRecord */

const SAFE_URL_SCHEME = /^(https?|ftp):\/\//i;

export const UserFolder = Object.freeze({
    COMPANY: "COMPANY",
    MY: "MY",
    RECENT: "RECENT",
    SHARED: "SHARED",
    TRASH: "TRASH",
});

export const WRITABLE_ROOTS = Object.freeze([UserFolder.COMPANY, UserFolder.MY]);

const SPECIAL_FOLDER_IDS = Object.freeze(Object.values(UserFolder));

export const DocumentsViewEvent = Object.freeze({
    OPEN_PREVIEW: "documents-open-preview",
    CLOSE_PREVIEW: "documents-close-preview",
    UPLOAD_FILES: "documents-upload-files",
    OPEN_AUTOMATIONS: "documents-open-automations",
    EXPAND_FOLDER: "documents-expand-folder",
});

export const SEARCH_PANEL_UPDATED = "documents-search-panel-updated";

export const PASTE_SHARE_LINKS = "documents-paste-share-links";

export const FOLDER_STORAGE_KEY = "searchpanel_documents_document";

/**
 * @param {unknown} folderId
 * @returns {boolean}
 */
export function isSpecialFolderId(folderId) {
    return SPECIAL_FOLDER_IDS.includes(folderId);
}

/**
 * @param {String} url
 * @return {String}
 */
export function toSafeDocumentUrl(url) {
    return SAFE_URL_SCHEME.test(url) ? url : `http://${url}`;
}

/**
 * @param {String} url
 */
export function openDocumentUrl(url) {
    window.open(toSafeDocumentUrl(url), "_blank", "noopener,noreferrer");
}

export function specialFolderDropRefusal() {
    return _t(
        "You can't create shortcuts in or move documents to this special folder.",
    );
}

/**
 * @param {number|String|false} userFolderId
 * @returns {number|String|false}
 */
export function toFolderValueId(userFolderId) {
    if (typeof userFolderId === "number") {
        return userFolderId;
    }
    if (typeof userFolderId !== "string" || !userFolderId) {
        return false;
    }
    return /^\d+$/.test(userFolderId) ? Number(userFolderId) : userFolderId;
}

/**
 * @param {RelationalModelRecord[]} documents
 * @return {{id: Number, name: String}[]}
 */
export function getCommonEmbeddedActions(documents) {
    if (!documents?.length) {
        return [];
    }
    let embeddedActionsMap = new Map(
        documents[0].data.available_embedded_actions_ids?.records.map((rec) => [
            rec.resId,
            rec.data.display_name,
        ]) || [],
    );
    for (const document of documents.slice(1)) {
        if (!embeddedActionsMap.size) {
            return [];
        }
        const newEmbeddedActionsMap = new Map();
        document.data.available_embedded_actions_ids?.records.forEach((r) => {
            if (embeddedActionsMap.has(r.resId)) {
                newEmbeddedActionsMap.set(r.resId, r.data.display_name);
            }
        });
        embeddedActionsMap = newEmbeddedActionsMap;
    }
    const embeddedActionsArray = Array.from(embeddedActionsMap.entries());
    return embeddedActionsArray.map(([id, name]) => ({ id, name }));
}

/**
 * @param {import("@web/ui/notification/notification_service").NotificationService} notification
 * @param {{title: string, documents: string[]}} warning
 */
export function notifyEmbeddedActionWarning(notification, warning) {
    notification.add(
        markup`<ul>${htmlJoin(warning.documents.map((d) => markup`<li>${d}</li>`))}</ul>`,
        { title: warning.title, type: "danger" },
    );
}
