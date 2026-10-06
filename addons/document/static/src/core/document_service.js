/** @odoo-module native */
import { DocumentsManageVersions } from "@document/components/document_manage_versions_panel/document_manage_versions_panel";
import { AccessRightsUpdateConfirmationDialog } from "@document/owl/components/access_update_confirmation_dialog/access_update_confirmation_dialog";
import { FOLDER_STORAGE_KEY, openDocumentUrl } from "@document/views/utils";
import { EventBus, markup, observe, proxy, toRaw } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { parseSearchQuery, router } from "@web/core/browser/router";
import { makeLogger } from "@web/core/debug/debug_logger";
import { now, serializeDate } from "@web/core/l10n/dates";
import { download, rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { Deferred } from "@web/core/utils/concurrency";
import { humanSize } from "@web/core/utils/format/binary";
import { debounce } from "@web/core/utils/timing";
import { session } from "@web/session";
import { ConfirmationDialog } from "@web/ui/dialog";

const log = makeLogger("document.service");

/**
 * Form field marking an upload as a document one. The upload bus is global:
 * a documents view reacts only to what it or this service sent. Not read by
 * the server.
 */
export const DOCUMENT_UPLOAD_MARKER = "documents_upload";

/**
 * What the service's bus carries to the mounted documents views, one name per
 * fact; a view's own bus (`documents-open-preview`, ...) speaks within it.
 */
export const DocumentsBusEvent = Object.freeze({
    /** something changed the documents: reload the tree and the records */
    RELOAD: "documents-reload",
    /** the selection emptied: the details panel goes back to the folder */
    FOCUS_FOLDER: "documents-focus-folder",
    /** an activity was scheduled or done in the chatter: `{ recordId }` */
    ACTIVITY_CHANGED: "documents-activity-changed",
});

/** Context key asking the server to refuse a move that changes access (tools.py). */
export const MOVE_ACCESS_CHECK = "documents_move_access_check";
const MOVE_CHANGES_ACCESS = "odoo.addons.document.tools.MoveChangesAccess";

export class DocumentService {
    constructor(env, services) {
        this.env = env;
        this.orm = services["orm"];
        this.action = services["action"];
        this.notification = services["notification"];
        this.dialog = services["dialog"];
        this.fileUpload = services["file_upload"];
        // unused here: ai_document's patch of start() subscribes through it
        this.busService = services["bus_service"];
        // visits are flushed together: every folder opened meanwhile, but only
        // the document the focus stopped on, and a token once
        this._pendingVisits = { folders: new Set(), document: undefined };
        this._flushVisits = debounce(() => this._sendVisits(), 1000, false);
        this.currentFolderAccessToken = null;
        this._urlOwners = 0;
        this.bus = new EventBus();
        this.userIsDocumentManager = false;
        this.userIsDocumentUser = false;
        this.userIsInternal = user.isInternalUser;
        this.hasFolderEditorAccess = false;
        const urlSearch = parseSearchQuery(browser.location.search);
        const { documents_init } = session;
        const openPreview =
            Boolean(urlSearch.documents_init_open_preview) ||
            documents_init?.open_preview;
        const documentId =
            Number(urlSearch.documents_init_document_id) || documents_init?.document_id;
        this._focusRequest = null;
        if (documentId) {
            this.requestFocus(documentId, { openPreview });
        }
        const userFolderId =
            urlSearch.documents_init_user_folder_id || documents_init?.user_folder_id;
        this._initData = { userFolderId };
        if (userFolderId) {
            browser.localStorage.setItem(FOLDER_STORAGE_KEY, userFolderId);
        }
        // The mounted view controller publishes how to build the selection's
        // actions; reactive so the control panel re-renders when the view
        // switches rather than reading a stale or empty slot.
        this.selectionActions = proxy({ provider: null });
    }

    /**
     * @returns {boolean}
     */
    _readChatterVisible() {
        try {
            return Boolean(
                JSON.parse(browser.localStorage.getItem("documentsChatterVisible")),
            );
        } catch {
            return false;
        }
    }

    /**
     * Asks the next primary documents view to load to show this document:
     * brought into its first page, selected, and previewed if asked. Made by
     * the tab's URL and by an action opening the app on a document.
     *
     * @param {number} documentId
     * @param {{openPreview?: boolean}} [options]
     */
    requestFocus(documentId, { openPreview = false } = {}) {
        this._focusRequest = { documentId, openPreview: Boolean(openPreview) };
        log.logic("requestFocus", () => this._focusRequest);
    }

    /**
     * @returns {{documentId: number, openPreview: boolean}|null} the pending
     *  request: read by a load, settled only by the one that publishes
     */
    get focusRequest() {
        return this._focusRequest;
    }

    /**
     * The request was shown (or found missing) by a published load; a
     * newer request made meanwhile stays pending.
     *
     * @param {{documentId: number, openPreview: boolean}} request
     */
    settleFocusRequest(request) {
        if (this._focusRequest === request) {
            this._focusRequest = null;
        }
    }

    async start() {
        [this.userIsDocumentManager, this.userIsDocumentUser] = await Promise.all([
            user.hasGroup("document.group_documents_manager"),
            user.hasGroup("document.group_documents_user"),
        ]);
        this.hasFolderEditorAccess = this.userIsInternal;
        if (!this.hasFolderEditorAccess) {
            try {
                const destinations = await this.orm.call(
                    "wizard.document.document.place.folder",
                    "get_any_editor_destination",
                );
                this.hasFolderEditorAccess = destinations.length > 0;
            } catch {
                // No operation wizard: nothing to move or duplicate into anyway.
            }
        }
        this.rightPanelReactive = observe(
            {
                visible: this.userIsInternal && this._readChatterVisible(),
                focusedRecord: null,
                previewedDocument: null,
            },
            () => {
                browser.localStorage.setItem(
                    "documentsChatterVisible",
                    this.rightPanelReactive.visible,
                );
            },
        );
    }

    /**
     * @param {number} documentId
     * @returns {Promise<String>}
     */
    async loadEmailContent(documentId) {
        if (!this._emailContentBatch) {
            this._emailContentBatch = { ids: new Set(), deferred: new Deferred() };
            Promise.resolve().then(() => this._flushEmailContentBatch());
        }
        const batch = this._emailContentBatch;
        batch.ids.add(documentId);
        return (await batch.deferred)[documentId];
    }

    async _flushEmailContentBatch() {
        const batch = this._emailContentBatch;
        this._emailContentBatch = null;
        try {
            const records = await this.orm.read(
                "document.document",
                [...batch.ids],
                ["raw"],
            );
            batch.deferred.resolve(
                Object.fromEntries(records.map((r) => [r.id, r.raw])),
            );
        } catch (error) {
            batch.deferred.reject(error);
        }
    }

    canUploadInFolder(folder) {
        if (!folder) {
            return false;
        }
        const userPermission = folder.target_user_permission || folder.user_permission;
        return (
            (typeof folder.id === "number" && userPermission === "edit") ||
            (this.userIsInternal && ["MY", "RECENT", false].includes(folder.id)) ||
            (this.userIsDocumentManager && folder.id === "COMPANY")
        );
    }

    /**
     * A link opens; a file downloads; a folder downloads as a zip.
     *
     * @param {Object} data a `document.document` read: type, url, access_token
     */
    async downloadDocument(data) {
        if (data.type === "url") {
            openDocumentUrl(data.url);
            return;
        }
        await download({
            data: {},
            url: `/documents/content/${encodeURIComponent(data.access_token)}`,
        });
    }

    async downloadDocuments(documents, resIds) {
        if (!resIds) {
            documents = documents.filter((rec) => !rec.isRequest());
            // links have nothing to zip: a lone link opens, a lone file downloads
            const files = documents.filter((rec) => rec.data.type !== "url");
            const single =
                documents.length === 1 ? documents[0] : files.length === 1 && files[0];
            if (single) {
                await this.downloadDocument(single.data);
                return;
            }
            resIds = files.map((rec) => rec.data.id);
        }
        // a selection of links and requests has nothing to zip; an empty
        // list would reach the server as file_ids="" and be refused
        if (!resIds.length) {
            return;
        }
        await download({
            data: {
                file_ids: resIds,
                zip_name: `documents-${serializeDate(now())}.zip`,
            },
            url: "/documents/zip",
        });
    }

    isEditable(document) {
        return (
            document &&
            typeof document.id === "number" &&
            document.user_permission === "edit" &&
            (document.user_folder_id !== "COMPANY" || this.userIsDocumentManager)
        );
    }

    /**
     * @param {number} documentId
     * @returns {Promise<boolean>} whether the document was renamed: both
     *      buttons close the dialog alike, only a save calls onSave
     */
    async openDialogRename(documentId) {
        let renamed = false;
        await new Promise((resolve) => {
            this.action.doAction(
                {
                    name: _t("Rename"),
                    type: "ir.actions.act_window",
                    res_model: "document.document",
                    res_id: documentId,
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        active_id: documentId,
                        dialog_size: "medium",
                        form_view_ref: "document.document_view_form_rename",
                    },
                },
                {
                    props: {
                        // replaces the dialog form's default onSave
                        // (action_info_builders), whose close it repeats
                        onSave: (record, params) => {
                            renamed = true;
                            if (params?.closable) {
                                this.action.doAction({
                                    type: "ir.actions.act_window_close",
                                });
                            }
                        },
                    },
                    onClose: resolve,
                },
            );
        });
        return renamed;
    }

    /**
     * @param {number} documentId
     * @param {() => Promise<void>} onVersionsChanged refreshes what a restored
     *  or deleted version changed: that document alone
     */
    openDialogManageVersions(documentId, onVersionsChanged) {
        this.dialog.add(DocumentsManageVersions, { documentId, onVersionsChanged });
    }

    async openSharingDialog(documentIds) {
        const action = await this.orm.call(
            "wizard.document.document.share",
            "action_open",
            [documentIds],
        );
        await this.action.doAction(action, { onClose: () => this.reload() });
    }

    async openOperationDialog({
        documents,
        attachmentId,
        operation = "move",
        onClose = () => {},
        context = {},
    }) {
        documents = documents || [];
        const doc0 = documents[0];
        let name;
        const single_values = { documentName: doc0?.name };
        const multiple_values = { numberOfDocuments: documents.length.toString() };
        if (operation === "move") {
            name =
                documents.length === 1
                    ? _t("Move: %(documentName)s", single_values)
                    : _t("Move: %(numberOfDocuments)s items", multiple_values);
        } else if (operation === "shortcut") {
            name =
                documents.length === 1
                    ? _t("Create shortcut to: %(documentName)s", single_values)
                    : _t(
                          "Create shortcuts for: %(numberOfDocuments)s items",
                          multiple_values,
                      );
        } else if (operation === "copy") {
            name =
                documents.length === 1
                    ? _t("Duplicate: %(documentName)s", single_values)
                    : _t("Duplicate: %(numberOfDocuments)s items", multiple_values);
        } else if (operation === "add") {
            name = _t("Add to documents");
        } else {
            name = operation;
        }
        return this.action.doAction(
            {
                name,
                type: "ir.actions.act_window",
                res_model: "wizard.document.document.place.folder",
                views: [[false, "form"]],
                target: "new",
            },
            {
                additionalContext: {
                    default_document_ids: documents.map((d) => d.id),
                    default_attachment_id: attachmentId || false,
                    default_operation: operation,
                    ...context,
                },
                onClose,
            },
        );
    }

    /**
     * @param {String} key
     * @param {Function} factory
     * @returns {Promise<any>}
     */
    _fetchOnce(key, factory) {
        this._onceCache ??= {};
        if (!this._onceCache[key]) {
            // a failure is not an answer: the next caller asks again
            this._onceCache[key] = factory().catch((error) => {
                delete this._onceCache[key];
                throw error;
            });
        }
        return this._onceCache[key];
    }

    /**
     * @returns {Promise<number>}
     */
    getDeletionDelay() {
        return this._fetchOnce("deletionDelay", () =>
            this.orm.call("document.document", "get_deletion_delay", [[]]),
        );
    }

    /** @returns {Promise<number>} */
    getMaxUploadSize() {
        return this._fetchOnce("maxUploadSize", () =>
            this.orm.call("document.document", "get_document_max_upload_limit"),
        );
    }

    /** @returns {Promise<String[]>} */
    getDetailsPanelResModels() {
        return this._fetchOnce("detailsPanelResModels", () =>
            this.orm.call("document.document", "get_details_panel_res_models"),
        );
    }

    async moveToTrash(documentIds) {
        const deletionDelay = await this.getDeletionDelay();
        const confirmed = await new Promise((resolve) => {
            const dialogProps = {
                title: _t("Move to trash"),
                body: _t(
                    "Items moved to the trash will be deleted forever after %(deletion_delay)s days.",
                    { deletion_delay: deletionDelay },
                ),
                confirmLabel: _t("Move to trash"),
                cancelLabel: _t("Discard"),
                confirm: async () => resolve(true),
                cancel: () => resolve(false),
            };
            this.dialog.add(ConfirmationDialog, dialogProps);
        });
        if (!confirmed) {
            return false;
        }
        await this.orm.call("document.document", "action_archive", [documentIds]);
        return true;
    }

    async goToServerActionsView() {
        const userHasAccessRight = await user.checkAccessRight(
            "ir.actions.server",
            "create",
        );
        if (!userHasAccessRight) {
            return this.notification.add(
                _t("Contact your Administrator to get access if needed."),
                {
                    title: _t("Access to Server Actions"),
                    type: "info",
                },
            );
        }

        return await this.action.doActionButton({
            name: "action_view_documents_server_action_view",
            type: "object",
            resModel: "ir.actions.server",
        });
    }

    /**
     * Runs a move checked by the server, which refuses it (moving nothing)
     * when it changes who can access the moved documents or what they
     * contain, and says what would change; once the user accepts that, runs
     * it again unchecked.
     *
     * @param {(context: Object) => Promise<any>} move
     * @param {string} folderName
     * @returns {Promise<boolean>} whether the documents moved
     */
    async moveConfirmingAccess(move, folderName) {
        try {
            await move({ [MOVE_ACCESS_CHECK]: true });
            return true;
        } catch (error) {
            if (error.data?.name !== MOVE_CHANGES_ACCESS) {
                throw error;
            }
            const changes = error.data.arguments[1];
            log.logic("move refused for its access changes", () => ({
                folderName,
                changes,
            }));
            const confirmed = await new Promise((resolve) => {
                this.dialog.add(AccessRightsUpdateConfirmationDialog, {
                    folderName,
                    changes,
                    confirm: async () => resolve(true),
                    cancel: () => resolve(false),
                });
            });
            if (confirmed) {
                await move({});
            }
            return confirmed;
        }
    }

    /**
     * @param {{all: number[], movableRecordIds: number[], nonMovableRecordIds: number[]}} records
     * @param {Object} targetFolder
     * @param {boolean} forceShortcut link instead of moving
     * @returns {Promise<boolean>} whether anything moved or was linked
     */
    async moveOrCreateShortcut(records, targetFolder, forceShortcut) {
        let message = "";
        let changed = false;
        const userFolderId = targetFolder.id.toString();
        if (forceShortcut) {
            await this.orm.call("document.document", "action_create_shortcut", [
                records.all,
                userFolderId,
            ]);
            changed = true;
            message =
                records.all.length === 1
                    ? _t("A shortcut has been created.")
                    : _t("%s shortcuts have been created.", records.all.length);
        } else {
            if (records.movableRecordIds.length) {
                message =
                    records.movableRecordIds.length === 1
                        ? _t("The document has been moved.")
                        : _t(
                              "%s documents have been moved.",
                              records.movableRecordIds.length,
                          );
                const moved = await this.moveConfirmingAccess(
                    (context) =>
                        this.orm.write(
                            "document.document",
                            records.movableRecordIds,
                            { user_folder_id: userFolderId },
                            { context },
                        ),
                    targetFolder.display_name,
                );
                if (!moved) {
                    return false;
                }
                changed = true;
            }
            if (records.nonMovableRecordIds.length) {
                this.notification.add(
                    _t(
                        "At least one document could not be moved due to access rights.",
                    ),
                    { type: "warning" },
                );
            }
        }
        if (message) {
            this.notification.add(message, { type: "success" });
        }
        return changed;
    }

    /**
     * @param {{movableRecordIds: number[], nonMovableRecordIds: number[]}} records
     * @returns {Promise<boolean>} whether anything moved
     */
    async moveToCompanyRoot(records) {
        if (!records.movableRecordIds.length) {
            this.notification.add(
                _t("You can't move this/those folder(s) to the Company root."),
                { type: "warning" },
            );
            return false;
        }
        const moved = await this.moveConfirmingAccess(
            (context) =>
                this.orm.write(
                    "document.document",
                    records.movableRecordIds,
                    { user_folder_id: "COMPANY" },
                    { context },
                ),
            _t("Company"),
        );
        if (!moved) {
            return false;
        }
        let message =
            records.movableRecordIds.length === 1
                ? _t("The document/folder has been moved to the Company root.")
                : _t(
                      "%s documents/folders have been moved to the Company root.",
                      records.movableRecordIds.length,
                  );
        if (records.nonMovableRecordIds.length) {
            message = markup`${message}<br/>${_t("At least one document hasn't been moved.")}`;
        }
        this.notification.add(message, {
            type: records.nonMovableRecordIds.length ? "warning" : "success",
        });
        return true;
    }

    /** @param {number[]} documentIds */
    async toggleFavorite(documentIds) {
        await this.orm.call("document.document", "action_toggle_user_favorite", [
            documentIds,
        ]);
    }

    get initData() {
        return this._initData;
    }

    reload() {
        this.bus.trigger(DocumentsBusEvent.RELOAD);
    }

    /**
     * The URL is the Documents app's: only a view of it (not a picker opened
     * over another app) writes a document's token there.
     *
     * @returns {() => void} to call when the view goes
     */
    registerURLOwner() {
        this._urlOwners++;
        return () => this._urlOwners--;
    }

    /**
     * @param {Object|false} [folderChange] the folder just opened
     * @param {Object[]|null} [inspectedDocuments]
     * @param {boolean} [forceInspected]
     */
    updateDocumentURL(folderChange, inspectedDocuments, forceInspected) {
        let accessToken = undefined;
        if (folderChange) {
            accessToken = folderChange.access_token;
            this.currentFolderAccessToken = accessToken;
        } else if (inspectedDocuments && inspectedDocuments.length === 1) {
            const record = inspectedDocuments[0];
            if (
                forceInspected ||
                record.selected ||
                record.isContainer ||
                this.rightPanelReactive.previewedDocument?.record.id === record.id
            ) {
                accessToken = record.data.access_token;
            }
        } else if (!inspectedDocuments || inspectedDocuments.length === 0) {
            accessToken = this.currentFolderAccessToken;
        }
        // the folder is remembered all the same: the view mounting next
        // writes it (updateDocumentURLRefresh). A portal user keeps the last
        // token: a bare /odoo/documents is the backend, which they may not enter
        if (this._urlOwners && (accessToken || this.userIsInternal)) {
            router.pushState({ access_token: accessToken || undefined });
        }
    }

    updateDocumentURLRefresh() {
        if (!this._urlOwners) {
            return;
        }
        const tokenToShow =
            this.focusedRecord?.data.access_token || this.currentFolderAccessToken;
        if (tokenToShow) {
            router.pushState({ access_token: tokenToShow });
        }
    }

    /**
     * Record a visit; browsing quickly through documents only counts the one
     * the user stopped on, while every folder opened counts.
     *
     * @param {String} accessToken
     * @param {"folder"|"document"} [kind]
     */
    logAccess(accessToken, kind = "document") {
        if (!accessToken) {
            return;
        }
        if (kind === "folder") {
            this._pendingVisits.folders.add(accessToken);
        } else {
            this._pendingVisits.document = accessToken;
        }
        this._flushVisits();
    }

    _sendVisits() {
        const { folders, document } = this._pendingVisits;
        const tokens = new Set([...folders, document].filter(Boolean));
        this._pendingVisits = { folders: new Set(), document: undefined };
        for (const token of tokens) {
            this._logAccess(token);
        }
    }

    /**
     * @param {String} accessToken
     */
    async _logAccess(accessToken) {
        if (!accessToken) {
            return;
        }
        log.logic("touch", () => ({ accessToken }));
        try {
            await rpc(`/documents/touch/${encodeURIComponent(accessToken)}`);
        } catch {
            // a visit that could not be recorded changes nothing on screen
        }
    }

    async getActions(folderId) {
        if (!this.userIsInternal) {
            return [];
        }
        return await this.orm.call("document.document", "get_documents_actions", [
            folderId,
        ]);
    }

    async enableAction(folderId, actionId) {
        return await this.orm.call("document.document", "action_folder_embed_action", [
            folderId,
            actionId,
        ]);
    }

    get focusedRecord() {
        return this.rightPanelReactive.focusedRecord;
    }

    focusRecord(record, forceSelected) {
        // the panel state is reactive: it hands back a proxy of the record
        log.logic("focusRecord", () => ({
            id: record?.id,
            changed: toRaw(this.focusedRecord) !== toRaw(record),
        }));
        if (toRaw(this.focusedRecord) !== toRaw(record)) {
            this.rightPanelReactive.focusedRecord = record;
            this.updateDocumentURL(null, record ? [record] : null, forceSelected);
            if (record) {
                this.logAccess(record.data.access_token);
            }
        }
    }

    toggleRightPanelVisibility() {
        this.rightPanelReactive.visible = !this.rightPanelReactive.visible;
    }

    setPreviewedDocument(document) {
        this.rightPanelReactive.previewedDocument = document;
        if (document) {
            this.focusRecord(document.record);
        }
    }

    /**
     * A file that goes straight to the cloud provider never crosses the
     * server, so the server's upload cap does not apply to it.
     *
     * @param {File} file
     * @returns {boolean}
     */
    isCloudUpload(file) {
        return (
            session.cloud_storage_min_file_size !== undefined &&
            file.size > session.cloud_storage_min_file_size &&
            !session.cloud_storage_unsupported_models?.includes("document.document")
        );
    }

    /**
     * @param {FileList|File[]} files
     * @param {String} accessToken
     * @param {Object} [context]
     * @param {Object} [param3]
     * @param {number|String} [param3.targetFolderId]
     */
    async uploadDocument(files, accessToken, context, { targetFolderId } = {}) {
        const fileArray = [...files];
        const maxUploadSize = await this.getMaxUploadSize();
        const cloudFiles = fileArray.filter((file) => this.isCloudUpload(file));
        // no cap is null: get_document_max_upload_limit answers None for 0
        const validFiles = fileArray.filter(
            (file) =>
                !cloudFiles.includes(file) &&
                (maxUploadSize == null || file.size <= maxUploadSize),
        );
        log.logic("uploadDocument", {
            files: fileArray.length,
            cloud: cloudFiles.length,
            valid: validFiles.length,
            maxUploadSize,
        });
        const encodedToken = encodeURIComponent(accessToken || "");
        const uploadRoute = `/documents/upload/${encodedToken}`;
        const trackTarget = (upload) => {
            const trackedUpload = upload && this.fileUpload.uploads[upload.id];
            if (trackedUpload && targetFolderId !== undefined) {
                trackedUpload.targetFolderId = targetFolderId;
            }
        };
        for (const file of cloudFiles) {
            trackTarget(
                await this.fileUpload.upload(uploadRoute, [file], {
                    directFile: file,
                    buildFormData: (formData) => {
                        this._buildUploadFormData(formData, context);
                        formData.append("cloud_storage", "1");
                        // the server stores an empty stand-in, sized from this
                        formData.append("file_size", file.size);
                    },
                }),
            );
        }
        if (validFiles.length !== 0) {
            const upload = await this.fileUpload.upload(uploadRoute, validFiles, {
                buildFormData: (formData) =>
                    this._buildUploadFormData(formData, context),
            });
            trackTarget(upload);
        }
        if (validFiles.length + cloudFiles.length >= fileArray.length) {
            return;
        }
        const message = _t(
            "Some files could not be uploaded (max size: %s).",
            humanSize(maxUploadSize),
        );
        this.notification.add(message, { type: "danger" });
    }

    /**
     * @param {FormData} formData
     * @param {Object} [context]
     */
    _buildUploadFormData(formData, context) {
        formData.append(DOCUMENT_UPLOAD_MARKER, "1");
        if (!context) {
            return;
        }
        for (const key of [
            "default_user_folder_id",
            "default_partner_id",
            "default_res_id",
            "default_res_model",
        ]) {
            if (context[key]) {
                formData.append(key.replace("default_", ""), context[key]);
            }
        }
        if (context.allowed_company_ids) {
            formData.append(
                "allowed_company_ids",
                JSON.stringify(context.allowed_company_ids),
            );
        }
        // not read by the server: the progress bars match their record by it
        if (context.document_id) {
            formData.append("document_id", context.document_id);
        }
    }
}

export const documentService = {
    dependencies: [
        "action",
        "bus_service",
        "dialog",
        "file_upload",
        "notification",
        "orm",
    ],
    async start(env, services) {
        const service = new DocumentService(env, services);
        await service.start();
        return service;
    },
};

registry.category("services").add("document.document", documentService);
