/** @odoo-module native */
import { DocumentsBusEvent } from "@document/core/document_service";
import {
    isDownloadAllowed,
    isLockedByOther,
    isTrashable,
} from "@document/views/document_actions";
import { useDocumentContext } from "@document/views/document_context";
import {
    getCommonEmbeddedActions,
    notifyEmbeddedActionWarning,
} from "@document/views/utils";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useBus, useService } from "@web/core/utils/hooks";
import { getSpecEvalContext } from "@web/model/relational_model";
import { ConfirmationDialog } from "@web/ui/dialog";

const log = makeLogger("document.model");

export const DocumentsModelMixin = (component) =>
    class extends component {
        // _loadData reorders the page around the document to restore and the
        // root reapplies the selection; a background cache refresh would set
        // the raw server page on the root and undo both
        static withCache = false;

        static useViewContext() {
            const viewContext = super.useViewContext();
            viewContext.documentsView = useDocumentContext().documentsView;
            return viewContext;
        }

        setup(params) {
            super.setup(...arguments);
            if (this.config.resModel === "document.document") {
                this.originalSelection = params.state?.sharedSelection;
            }
            // set with each root (_createRoot); read by shortcuts before the
            // first one exists
            this.shortcutTargetRecords = [];
            // the requested document to preview once the controller renders it
            this.pendingPreviewId = undefined;
            this.action = useService("action");
            this.dialogService = useService("dialog");
            this.documentService = useService("document.document");
            this.notification = useService("notification");
            // the chatter's activities show on the card and in the list columns
            useBus(
                this.documentService.bus,
                DocumentsBusEvent.ACTIVITY_CHANGED,
                ({ detail }) =>
                    this.root?.records
                        ?.find((record) => record.resId === detail.recordId)
                        ?.load(),
            );
        }

        exportSelection() {
            // the selection, not targetRecords: a preview narrows those to itself
            return this.root.selection.map((rec) => rec.resId);
        }

        /**
         * @override
         */
        async load(params = {}) {
            const selection = this.root?.selection;
            if (
                this.originalSelection === undefined &&
                selection &&
                selection.length > 0
            ) {
                this.originalSelection = selection.map((rec) => rec.resId);
            }
            const nextParams =
                this.config.resModel === "document.document"
                    ? {
                          ...params,
                          context: {
                              ...(params.context ?? this.config.context),
                              skip_res_field_check: true,
                          },
                      }
                    : params;
            const previousRoot = this.root;
            const res = await super.load(nextParams);
            if (this.config.resModel !== "document.document") {
                return res;
            }
            // a load superseded by a newer one publishes no root: what
            // follows belongs to the newer load
            if (this.root === previousRoot) {
                log.logic("load superseded");
                return res;
            }
            const root = this.root;
            // the preview shows records of the root just replaced
            this.viewContext.documentsView.bus.trigger("documents-close-preview");
            this._reapplySelection();
            this._computeFileSize();
            log.logic("loaded", () => ({
                records: root.records?.length,
                groups: root.groups?.length,
                selection: root.selection?.length,
                shortcutTargets: this.shortcutTargetRecords.length,
            }));
            return res;
        }

        /**
         * @override the document to restore is fetched with the page, under
         * the same abort signal
         */
        async _loadData(config, cache, signal) {
            const data = await super._loadData(config, cache, signal);
            if (config.resModel === "document.document" && !config.isMonoRecord) {
                await this._loadDocumentToRestore(config, data, cache, signal);
                data.shortcutTargets = this.orm.isSample
                    ? []
                    : await this._loadShortcutTargets(config, data, cache, signal);
            }
            return data;
        }

        /**
         * @override the selection is reapplied before the root is published:
         * its views render as soon as it is, and would see a root with no
         * selection
         */
        _createRoot(config, data) {
            const focusedId = this._settleFocus(data?.focus);
            const root = super._createRoot(...arguments);
            if (config.resModel === "document.document") {
                // fetched with the page: a shortcut never renders without them
                this.shortcutTargetRecords = (data?.shortcutTargets ?? []).map(
                    (target) => this._createRecordDatapoint(target),
                );
            }
            // the empty root of a first load has no records to select yet
            if (config.resModel === "document.document" && root.records?.length) {
                this._reapplySelection(root);
            }
            // selected here, not by the record's setup: a reload reuses records
            const focused =
                focusedId && root.records?.find((r) => r.resId === focusedId);
            if (focused) {
                focused.selected = true;
            }
            return root;
        }

        _reapplySelection(root = this.root) {
            const records = root.records;
            if (!records) {
                return;
            }
            if (this.originalSelection?.length) {
                const originalSelection = new Set(this.originalSelection);
                records.forEach((record) => {
                    record.selected = originalSelection.has(record.resId);
                });
            }
            delete this.originalSelection;
        }

        /** The bytes the loaded page weighs: what the folder's details show. */
        _computeFileSize() {
            const items = this.root.groups
                ? this.root.groups.map((group) => group.aggregates.file_size)
                : (this.root.records ?? []).map((record) => record.data.file_size);
            this.fileSize = items.reduce((total, size) => total + (size || 0), 0);
        }

        /**
         * The documents the page's shortcuts point to, read like the page.
         *
         * @returns {Promise<Object[]>} their raw data
         */
        async _loadShortcutTargets(config, data, cache, signal) {
            const rawRecords = (node) => [
                ...(node.records ?? []),
                ...(node.groups ?? []).flatMap(rawRecords),
            ];
            const targetIds = [
                ...new Set(
                    rawRecords(data)
                        .map((record) => record.shortcut_document_id?.id)
                        .filter(Boolean),
                ),
            ];
            if (!targetIds.length) {
                return [];
            }
            return this.loadRecords(
                { ...config, resIds: targetIds },
                getSpecEvalContext(config),
                cache,
                signal,
            );
        }

        _createRecordDatapoint(data, mode = "readonly") {
            return new this.constructor.Record(
                this,
                {
                    context: this.config.context,
                    activeFields: this.config.activeFields,
                    resModel: this.config.resModel,
                    fields: this.config.fields,
                    resId: data.id || false,
                    resIds: data.id ? [data.id] : [],
                    isMonoRecord: true,
                    mode,
                },
                data,
                { manuallyAdded: !data.id },
            );
        }

        /**
         * Reload the folder tree and, through the search update it notifies,
         * the records: loading them here as well read every page twice.
         */
        async _notifyChange() {
            log.logic("notifyChange");
            await this.viewContext.searchModel._reloadSearchModel(true);
            this.documentService.setPreviewedDocument(null);
        }

        get isDomainSelected() {
            return (
                this.root.isDomainSelected &&
                !this.documentService.rightPanelReactive.previewedDocument
            );
        }

        getResIds(extraDomain) {
            if (extraDomain) {
                const newDomain = Domain.and([this.root.domain, extraDomain]).toList();
                return this.orm.search("document.document", newDomain, {
                    limit: this.activeIdsLimit,
                    context: this.root.context,
                });
            }
            return this.root.getResIds(true);
        }

        get targetRecords() {
            return this.documentService.rightPanelReactive.previewedDocument
                ? [this.documentService.rightPanelReactive.previewedDocument.record]
                : this.root.selection;
        }

        get canManageVersions() {
            if (this.targetRecords.length !== 1) {
                return false;
            }
            const singleSelection = this.targetRecords[0];
            const currentFolder = this.viewContext.searchModel.getSelectedFolder();
            return (
                this.documentService.userIsInternal &&
                singleSelection &&
                currentFolder?.id !== "TRASH" &&
                singleSelection.data.type === "binary" &&
                singleSelection.data.attachment_id &&
                !this.isLockedByOther(singleSelection.data) &&
                isDownloadAllowed(singleSelection.data)
            );
        }

        /** @param {Object} data */
        isLockedByOther(data) {
            return isLockedByOther(data, this.documentService.userIsDocumentManager);
        }

        /** @param {Object} data */
        isTrashable(data) {
            const { searchModel } = this.viewContext;
            return isTrashable(data, {
                userIsDocumentManager: this.documentService.userIsDocumentManager,
                folderPermission: (folderId) =>
                    searchModel.getFolderById(folderId)?.user_permission,
            });
        }

        /** What onArchive trashes: the trashable ones, all of them editable. */
        get canArchiveRecords() {
            const documents = this.targetRecords.map((r) => r.data);
            return (
                this.documentService.userIsInternal &&
                documents.every((d) => d.user_permission === "edit") &&
                documents.some((d) => this.isTrashable(d))
            );
        }

        get canDeleteRecords() {
            const documents = this.targetRecords.map((r) => r.data);
            if (!documents.length) {
                return false;
            }
            if (this.documentService.userIsInternal) {
                return documents.some((d) => !d.active);
            }
            return documents.every(
                (r) =>
                    r.owner_id?.id === user.userId &&
                    ["binary", "url"].includes(r.type) &&
                    typeof r.folder_id?.id === "number" &&
                    this.viewContext.searchModel.getFolderById(r.folder_id.id)
                        .user_permission === "edit",
            );
        }

        get canDuplicateRecords() {
            return (
                this.documentService.hasFolderEditorAccess &&
                this.targetRecords.every(
                    (r) =>
                        !this.isLockedByOther(r.data) &&
                        r.data.active &&
                        // the copy would be its copier's to download
                        (r.data.type !== "binary" || isDownloadAllowed(r.data)),
                )
            );
        }

        get canMoveRecords() {
            return (
                this.documentService.hasFolderEditorAccess &&
                this.targetRecords.some((r) => r.data.user_can_move)
            );
        }

        async onCopyLinks() {
            const urls = this.isDomainSelected
                ? (
                      await this.orm.read("document.document", await this.getResIds(), [
                          "access_url",
                      ])
                  ).map((d) => d.access_url)
                : this.targetRecords.map((d) => d.data.access_url);
            const linksToShare = urls.length > 1 ? urls.join(", ") : urls[0];

            await browser.navigator.clipboard.writeText(linksToShare);
            const message =
                urls.length > 1
                    ? _t("Links copied to clipboard!")
                    : _t("Link copied to clipboard!");
            this.notification.add(message, { type: "success" });
        }

        /**
         * Stars or unstars each document for the current user, then refreshes
         * what shows a star: those records, and the folder tree for a folder.
         *
         * @param {Object[]} records
         */
        async toggleFavorite(records) {
            if (!records.length) {
                return;
            }
            await this.documentService.toggleFavorite(records.map((r) => r.resId));
            await Promise.all([
                ...records.map((record) => record.load()),
                records.some((record) => record.data.type === "folder") &&
                    this.viewContext.searchModel._reloadSearchPanel(),
            ]);
        }

        async onToggleLock() {
            if (this.targetRecords.length !== 1) {
                return;
            }
            const record = this.targetRecords[0];
            // a lock changes that document alone: no folder tree to refetch,
            // and a preview open on it stays open
            const toggle = async () => {
                await this.orm.call("document.document", "toggle_lock", [
                    record.data.id,
                ]);
                await record.load();
            };
            if (record.data.lock_uid && record.data.lock_uid.id !== user.userId) {
                this.dialogService.add(ConfirmationDialog, {
                    title: _t("Warning"),
                    body: _t(
                        "This document is locked by %s.\nAre you sure you want to unlock it?",
                        record.data.lock_uid.display_name,
                    ),
                    confirmLabel: _t("Unlock"),
                    confirm: toggle,
                    cancelLabel: _t("Discard"),
                    cancel: () => {},
                });
            } else {
                await toggle();
            }
        }

        async onToggleRightPanel() {
            await this.documentService.toggleRightPanelVisibility();
        }

        /**
         * What an operation wizard acts on: every matching document when the
         * domain is selected (unnamed: the wizard titles them by count).
         *
         * @param {Object[]} records
         * @returns {Promise<{id: number, name?: string}[]>}
         */
        async _operationDocuments(records) {
            if (this.isDomainSelected) {
                return (await this.getResIds()).map((id) => ({ id }));
            }
            return records.map((record) => ({
                id: record.data.id,
                name: record.data.name,
            }));
        }

        /** @param {"shortcut"|"copy"|"move"} operation */
        async _openOperationDialog(operation, records) {
            await this.documentService.openOperationDialog({
                documents: await this._operationDocuments(records),
                operation,
                onClose: () => this._notifyChange(),
            });
        }

        async onCreateShortcut() {
            await this._openOperationDialog("shortcut", this.targetRecords);
        }

        async onDelete() {
            const records = this.isDomainSelected
                ? null
                : this.documentService.userIsInternal
                  ? this.targetRecords.filter((r) => !r.data.active)
                  : this.targetRecords;
            if (records && !records.length) {
                return;
            }
            const confirmed = await new Promise((resolve) => {
                const dialogProps = {
                    title: _t("Delete permanently"),
                    body:
                        !records || records.length > 1
                            ? _t(
                                  "Are you sure you want to permanently erase the selected documents?",
                              )
                            : _t(
                                  "Are you sure you want to permanently erase the selected document?",
                              ),
                    confirmLabel: _t("Delete permanently"),
                    cancelLabel: _t("Discard"),
                    confirm: async () => resolve(true),
                    cancel: () => resolve(false),
                };
                this.dialogService.add(ConfirmationDialog, dialogProps);
            });
            if (!confirmed) {
                return;
            }
            // not root.deleteRecords: it reloads the records, and so does
            // _notifyChange along with the folder tree
            const resIds = records
                ? records.map((record) => record.resId)
                : this.documentService.userIsInternal
                  ? await this.getResIds([["active", "=", false]])
                  : await this.getResIds();
            await this.orm.unlink("document.document", resIds, {
                context: this.root.context,
            });
            await this._notifyChange();
        }

        /** @returns {Array} what a lock leaves this user to trash, as a domain */
        get _notLockedByOtherDomain() {
            if (this.documentService.userIsDocumentManager) {
                return [];
            }
            return Domain.or([
                [["lock_uid", "=", false]],
                [["lock_uid", "=", user.userId]],
            ]).toList();
        }

        async onArchive() {
            const records = this.targetRecords.filter((r) => this.isTrashable(r.data));
            const recordIds = this.isDomainSelected
                ? await this.getResIds(this._notLockedByOtherDomain)
                : records.map((rec) => rec.data.id);
            if (await this.documentService.moveToTrash(recordIds)) {
                await this._notifyChange();
            }
        }

        async onDuplicate() {
            await this._openOperationDialog("copy", this.targetRecords);
        }

        onManageVersions() {
            const documentId = this.targetRecords[0].data.id;
            this.documentService.openDialogManageVersions(documentId, async () => {
                // the preview holds the content it opened with
                const { previewedDocument } = this.documentService.rightPanelReactive;
                if (previewedDocument?.record.resId === documentId) {
                    this.viewContext.documentsView.bus.trigger(
                        "documents-close-preview",
                    );
                }
                // a group's size is an aggregate only the server recomputes
                const record = this.root.records?.find((r) => r.resId === documentId);
                log.logic("versions changed", () => ({
                    documentId,
                    found: Boolean(record),
                }));
                if (this.root.groups || !record) {
                    await this.load();
                } else {
                    await record.load();
                    this._computeFileSize();
                }
            });
        }

        async onRestore() {
            const records = this.targetRecords.filter((r) => !r.data.active);
            const recordIds = this.isDomainSelected
                ? await this.getResIds([["active", "=", false]])
                : records.map((r) => r.data.id);
            await this.orm.call("document.document", "action_unarchive", [recordIds]);
            await this.viewContext.searchModel._reloadSearchModel(true);
        }

        onSplitPDF() {
            const documents = this.targetRecords;
            if (!documents?.length || !documents.every((d) => d.isPdf())) {
                return;
            }

            this.viewContext.documentsView.bus.trigger("documents-open-preview", {
                documents: documents,
                mainDocument: this.targetRecords[0],
                isPdfSplit: true,
                embeddedActions: getCommonEmbeddedActions(documents),
            });
        }

        async onRename() {
            if (this.targetRecords.length !== 1) {
                return;
            }
            if (
                await this.documentService.openDialogRename(
                    this.targetRecords[0].data.id,
                )
            ) {
                await this._notifyChange();
            }
        }

        async onShare() {
            const documentIds = this.isDomainSelected
                ? await this.getResIds()
                : this.targetRecords.map((d) => d.data.id);
            await this.documentService.openSharingDialog(documentIds);
        }

        async onMove() {
            await this._openOperationDialog(
                "move",
                this.targetRecords.filter((r) => r.data.user_can_move),
            );
        }

        async onDoAction(actionId) {
            const documentIds = this.isDomainSelected
                ? await this.getResIds()
                : this.targetRecords.map((record) => record.data.id);
            await this.executeEmbeddedAction(documentIds, actionId);
        }

        /**
         * @param {number[]} documentIds
         * @param {number} actionId
         * @param {Object} [options]
         * @param {boolean} [options.reload] reload the view afterwards; the
         *      PDF splitter reloads once it closes instead
         * @param {boolean} [options.navigate] run a returned action that can
         *      leave the view; false while a dialog over it must stay open,
         *      which lets only notifications through
         */
        async executeEmbeddedAction(
            documentIds,
            actionId,
            { reload = true, navigate = true } = {},
        ) {
            const action = await this.orm.call(
                "document.document",
                "action_execute_embedded_action",
                [actionId],
                {
                    context: {
                        active_model: "document.document",
                        active_ids: documentIds,
                    },
                },
            );
            const isNotification = action?.tag === "display_notification";
            log.logic("embedded action", () => ({
                actionId,
                documents: documentIds.length,
                result: action?.warning ? "warning" : (action?.tag ?? action?.type),
                reload,
                navigate,
            }));
            if (action?.warning) {
                // The server refused some of the documents; nothing to open.
                notifyEmbeddedActionWarning(this.notification, action.warning);
            } else if (isNotification) {
                // the client executor calls onClose for a notification too:
                // none is passed, the reload below is the only one
                await this.action.doAction(action);
            } else if (action && navigate) {
                await this.action.doAction(action, {
                    onClose: () => reload && this._notifyChange(),
                });
                return;
            }
            if (reload) {
                await this._notifyChange();
            }
        }

        async onDownload() {
            if (this.isDomainSelected) {
                const domain = Domain.and([
                    [["type", "!=", "url"]],
                    Domain.or([
                        [["type", "=", "folder"]],
                        [["attachment_id", "!=", false]],
                        [["shortcut_document_id.attachment_id", "!=", false]],
                    ]),
                ]);
                const resIds = await this.getResIds(domain);
                await this.documentService.downloadDocuments(
                    this.targetRecords,
                    resIds,
                );
            } else {
                await this.documentService.downloadDocuments(this.targetRecords);
            }
        }
        /**
         * Brings the requested document into the page being loaded. The
         * request is only read here: a load superseded by a newer one is
         * dropped, and the load that publishes settles it (_createRoot).
         */
        async _loadDocumentToRestore(config, data, cache, signal) {
            // a picker in a dialog is not the view the request was made for
            const request =
                data.records && !config.context.documents_view_secondary
                    ? this.documentService.focusRequest
                    : null;
            if (!request) {
                return;
            }
            const { documentId } = request;
            const index = data.records.findIndex((r) => r.id === documentId);
            if (index !== -1) {
                data.records.unshift(...data.records.splice(index, 1));
                data.focus = { request, found: true };
                return;
            }
            log.logic("restore outside the page", () => ({ documentId }));
            const missingData = await super._loadData(
                {
                    ...config,
                    domain: Domain.and([
                        config.domain,
                        [["id", "=", documentId]],
                    ]).toList(),
                    limit: 1,
                },
                cache,
                signal,
            );
            const found = Boolean(missingData?.records?.length);
            if (found) {
                data.records.unshift(missingData.records[0]);
                if (config.limit && data.records.length > config.limit) {
                    data.records.pop();
                }
            }
            data.focus = { request, found };
        }

        /**
         * @param {{request: Object, found: boolean}} [focus]
         * @returns {number|undefined} the document to select
         */
        _settleFocus(focus) {
            if (!focus) {
                return;
            }
            const { request, found } = focus;
            this.documentService.settleFocusRequest(request);
            if (!found) {
                this.notification.add(_t("Document not found or inaccessible."), {
                    type: "danger",
                });
                return;
            }
            this.pendingPreviewId = request.openPreview
                ? request.documentId
                : undefined;
            return request.documentId;
        }
    };
