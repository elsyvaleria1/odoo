/** @odoo-module native */
import { DocumentFile } from "@document/attachments/document_file";
import {
    DOCUMENT_UPLOAD_MARKER,
    DocumentsBusEvent,
} from "@document/core/document_service";
import { PdfManager } from "@document/owl/components/pdf_manager/pdf_manager";
import {
    provideDocumentContext,
    useDocumentContext,
} from "@document/views/document_context";
import { DocumentsViewEvent, UserFolder, WRITABLE_ROOTS } from "@document/views/utils";
import { EventBus, onMounted, onWillDestroy, onWillUnmount, toRaw } from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { FileUploadEvent } from "@web/core/events";
import { useSearchModel } from "@web/core/search_model_hooks";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useBus, useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { provideViewModel, useViewModel } from "@web/model/model";
import { PromoteStudioAutomationDialog } from "@web/webclient/promote_studio/promote_studio_dialog";

const log = makeLogger("document.hooks");

/** Read by the views' own logic (details panel, action menus, drag and drop), whatever the arch shows. */
export const DOCUMENTS_VIEW_REQUIRED_FIELDS = [
    "lock_uid",
    "is_locked_by_other",
    "user_can_move",
    "user_can_trash",
    "shortcut_document_id",
    "res_name",
    "res_model_name",
    "file_size",
    "res_model",
    "mail_alias_domain_count",
    "alias_name",
    "alias_domain_id",
    "alias_email",
    "create_activity_type_id",
    "type",
    "name",
    "folder_id",
    "company_id",
    "owner_id",
    "user_permission",
    "partner_id",
    "tag_ids",
    "is_download_blocked",
    "access_via_link",
];

/**
 * Reload the search panel and the records of a documents view, in that order.
 * The one spelling behind the RELOAD bus event and the cog items.
 */
export async function reloadDocumentsView(env) {
    await env.model._notifyChange();
}

export function preSuperSetup() {
    provideDocumentContext({
        documentsView: {
            bus: new EventBus(),
        },
    });
}

export function useDocumentView(component, helpers) {
    const props = component.props;
    const orm = useService("orm");
    const notification = useService("notification");
    const dialogService = useService("dialog");
    const action = useService("action");
    const documentService = useService("document.document");

    provideViewModel(component.model);
    const ui = useService("ui");
    const env = {
        documentsView: useDocumentContext().documentsView,
        get isSmall() {
            return ui.isSmall;
        },
        model: useViewModel(),
        searchModel: useSearchModel(),
    };
    const bus = env.documentsView.bus;

    const _openAutomations = async ({ folderId, folderDisplayName }) => {
        const checkAutomationRule = await orm.call(
            "document.document",
            "check_automation_available",
        );
        if (!checkAutomationRule) {
            return dialogService.add(PromoteStudioAutomationDialog, {
                title: _t("Odoo Studio - Customize workflows in minutes"),
            });
        }
        const userHasAccessRight = await user.checkAccessRight(
            "automation.rule",
            "create",
        );
        if (!userHasAccessRight) {
            return notification.add(
                _t("Contact your Administrator to get access if needed."),
                {
                    title: _t("Access to Automations"),
                    type: "info",
                },
            );
        }
        const documentsModelId = await orm.search(
            "ir.model",
            [["model", "=", "document.document"]],
            { limit: 1 },
        );
        return await action.doAction("automation.automation_act", {
            additionalContext: {
                active_test: false,
                default_model_id: documentsModelId[0],
                search_default_model_id: documentsModelId[0],
                default_name: _t("Put in %s", folderDisplayName),
                default_filter_domain: [["folder_id", "in", [folderId]]],
                default_trigger: "on_create_or_write",
            },
        });
    };

    /**
     * @returns {number|false}
     */
    const selectedRealFolderId = () => {
        const folderId = env.searchModel.getSelectedFolderId();
        return typeof folderId === "number" ? folderId : false;
    };

    /**
     * A request or a link is made in a form over the view, in the open folder
     * and for the record the view is scoped to; the view reloads after.
     *
     * @param {string} actionXmlId
     * @param {Object} context what this form adds
     */
    const openCreateForm = (actionXmlId, context) =>
        action.doAction(actionXmlId, {
            additionalContext: {
                default_partner_id: props.context.default_partner_id || false,
                default_folder_id: selectedRealFolderId(),
                default_res_id: props.context.default_res_id || false,
                default_res_model: props.context.default_res_model || false,
                ...context,
            },
            fullscreen: env.isSmall,
            onClose: async () => {
                await env.model.load();
                env.model.notify();
            },
        });

    // the base controller saves and restores the scroll; this adds the selection
    useSetupAction({
        getGlobalState: () => ({
            sharedSelection: component.model.exportSelection(),
        }),
    });

    useBus(bus, DocumentsViewEvent.OPEN_AUTOMATIONS, (ev) => {
        _openAutomations(ev.detail);
    });

    if (!env.searchModel.context.documents_view_secondary) {
        let releaseURL;
        onMounted(() => {
            releaseURL = documentService.registerURLOwner();
            documentService.updateDocumentURLRefresh();
        });
        onWillUnmount(() => releaseURL?.());
    }

    return {
        orm,
        notification,
        dialogService,
        actionService: action,
        documentsPreview: useDocumentsViewFilePreviewer(component, env, helpers),
        canUploadInFolder: (folder) => documentService.canUploadInFolder(folder),
        ...useDocumentsViewFileUpload(component, env),
        userIsInternal: documentService.userIsInternal,
        userIsDocumentManager: documentService.userIsDocumentManager,
        onClickDocumentsRequest: () =>
            openCreateForm("document.action_request_form", {
                default_requestee_id: props.context.default_partner_id || false,
            }),
        onClickDocumentsAddUrl: () =>
            openCreateForm("document.action_url_form", {
                default_type: "url",
                ...(env.searchModel.getSelectedFolderId() === UserFolder.COMPANY
                    ? { default_owner_id: false }
                    : {}),
            }),
        onClickAddFolder: () => {
            const currentFolder = env.searchModel.getSelectedFolderId();
            // All, Recent, Shared and Trash cannot hold a folder: it goes to My Drive
            const parentFolder =
                currentFolder &&
                ![UserFolder.RECENT, UserFolder.SHARED, UserFolder.TRASH].includes(
                    currentFolder,
                )
                    ? currentFolder
                    : UserFolder.MY;
            action.doAction("document.action_folder_form", {
                additionalContext: {
                    default_type: "folder",
                    default_user_folder_id: parentFolder.toString(),
                    ...(parentFolder === UserFolder.COMPANY
                        ? { default_access_internal: "edit" }
                        : {}),
                },
                fullscreen: env.isSmall,
                onClose: async () => {
                    await env.searchModel._reloadSearchModel(true);
                    bus.trigger(DocumentsViewEvent.EXPAND_FOLDER, {
                        folderId: parentFolder,
                    });
                },
            });
        },
    };
}

/**
 * @param {Object} component the documents view's controller
 * @param {Object} env what useDocumentView gathered: documentsView, model, searchModel
 * @param {Object} helpers
 */
function useDocumentsViewFilePreviewer(
    component,
    env,
    { setPreviewStore, isRecordPreviewable = () => true },
) {
    const bus = env.documentsView.bus;
    /** @type {import("@document/core/document_service").DocumentService} */
    const documentService = useService("document.document");
    const orm = useService("orm");

    const documentsViewEl = () =>
        component.rootRef?.el?.querySelector(".o_documents_view");
    /** The files of the preview this view shows, if it shows one. */
    let shownFiles = null;
    /** Whether the document the service says is previewed is one of ours. */
    const previewsOurs = () =>
        Boolean(shownFiles) &&
        shownFiles.includes(
            toRaw(documentService.rightPanelReactive.previewedDocument),
        );
    /**
     * Closes this view's preview. The details panel stays on the document
     * last shown, and the keyboard goes back to its card or row.
     */
    const closePreview = () => {
        if (!shownFiles) {
            return;
        }
        const lastShown = previewsOurs()
            ? toRaw(documentService.rightPanelReactive.previewedDocument)
            : null;
        if (lastShown) {
            documentService.setPreviewedDocument(null);
        }
        shownFiles = null;
        documentsViewEl()?.classList.remove("overflow-hidden");
        setPreviewStore({});
        if (lastShown) {
            component.rootRef?.el
                ?.querySelector(`[data-id="${CSS.escape(lastShown.record.id)}"]`)
                ?.focus();
        }
    };
    const open = async ({ documents, mainDocument, isPdfSplit, embeddedActions }) => {
        const openPdfSplitter = (documents) => {
            let newDocumentIds = [];
            // originals every page was deleted from (none split)
            const emptiedIds = new Set();
            component.dialogService.add(
                PdfManager,
                {
                    documents: documents.map((doc) => doc.data),
                    embeddedActions,
                    userFolderId: env.searchModel.getSelectedFolderId(),
                    onProcessDocuments: async ({
                        documentIds,
                        actionId,
                        exit,
                        emptiedDocumentIds,
                    }) => {
                        for (const id of emptiedDocumentIds ?? []) {
                            emptiedIds.add(id);
                        }
                        if (documentIds && documentIds.length) {
                            newDocumentIds = [
                                ...new Set(newDocumentIds.concat(documentIds)),
                            ];
                        }
                        if (actionId) {
                            await component.model.executeEmbeddedAction(
                                documentIds,
                                actionId,
                                { reload: false, navigate: exit },
                            );
                        }
                    },
                },
                {
                    onClose: async () => {
                        if (!newDocumentIds.length && !emptiedIds.size) {
                            return;
                        }
                        // an original is archived by the split itself when the
                        // splitter asked for it, and one every page was deleted
                        // from goes to the trash: neither is unlinked, which
                        // would purge it past the trash
                        log.logic("pdfSplitterClosed", {
                            created: newDocumentIds,
                            trashed: [...emptiedIds],
                        });
                        if (emptiedIds.size) {
                            await orm.call("document.document", "action_archive", [
                                [...emptiedIds],
                            ]);
                        }
                        await component.model.load();
                        for (const record of env.model.root.records.filter((r) =>
                            newDocumentIds.includes(r.resId),
                        )) {
                            record.toggleSelection(true);
                        }
                    },
                },
            );
        };
        if (isPdfSplit) {
            setPreviewStore({});
            openPdfSplitter(documents);
            return;
        }
        const documentsRecords = (
            (documents.length === 1 && component.model.root.records) ||
            documents
        )
            .filter((rec) => isRecordPreviewable(rec) && rec.isViewable())
            .map((rec) =>
                DocumentFile.fromRecord(rec, {
                    loadEmailContent: (documentId) =>
                        documentService.loadEmailContent(documentId),
                }),
            );
        documentsViewEl()?.classList.add("overflow-hidden");
        const selectedDocument = documentsRecords.find(
            (file) => file.record.resId === (mainDocument || documents[0]).resId,
        );
        shownFiles = documentsRecords;
        // published before the viewer renders, which then follows its own
        // next and previous
        documentService.setPreviewedDocument(selectedDocument);
        setPreviewStore({
            files: documentsRecords,
            startIndex: documentsRecords.indexOf(selectedDocument),
            folderId: env.searchModel.getSelectedFolderId(),
            close: closePreview,
        });
    };

    useBus(bus, DocumentsViewEvent.OPEN_PREVIEW, (ev) => {
        component.onOpenDocumentsPreview(ev.detail);
    });
    useBus(bus, DocumentsViewEvent.CLOSE_PREVIEW, closePreview);
    // the previewed document is the service's, the preview the view's: a view
    // left with its preview open (Back, a menu) takes that preview with it
    onWillDestroy(() => {
        log.lifecycle("previewer destroyed", () => ({
            controller: component.constructor.name,
            ownsPreview: previewsOurs(),
        }));
        if (previewsOurs()) {
            documentService.setPreviewedDocument(null);
        }
        shownFiles = null;
    });

    return { open, close: closePreview };
}

/**
 * @param {Object} component the documents view's controller
 * @param {Object} env what useDocumentView gathered: documentsView, model, searchModel
 */
function useDocumentsViewFileUpload(component, env) {
    const bus = env.documentsView.bus;
    const fileUpload = useService("file_upload");
    const documentService = useService("document.document");

    // the upload bus carries every upload of the app: chatter files, tracebacks...
    const isDocumentUpload = (upload) =>
        Boolean(upload.data?.get?.(DOCUMENT_UPLOAD_MARKER));

    useBus(documentService.bus, DocumentsBusEvent.RELOAD, () =>
        reloadDocumentsView(env),
    );

    // uploads finishing together (every cloud file is an upload of its own)
    // load the view once and leave all their documents selected, instead of
    // each reloading it and replacing the others' selection
    const uploadedIds = new Set();
    const showUploaded = useDebounced(async () => {
        const ids = [...uploadedIds];
        uploadedIds.clear();
        await env.model.load();
        if (!ids.length) {
            return;
        }
        component.model.root.selection.forEach((r) => r.toggleSelection(false));
        const newRecords = env.model.root.records.filter((r) => ids.includes(r.resId));
        newRecords.forEach((record) => record.toggleSelection(true));
        documentService.focusRecord(newRecords[0]);
    }, 150);

    useBus(fileUpload.bus, FileUploadEvent.LOADED, (ev) => {
        const { upload } = ev.detail;
        if (!isDocumentUpload(upload)) {
            return;
        }
        const { response } = upload;
        const documentIds = Array.isArray(response) ? response : response?.document_ids;
        for (const id of Array.isArray(documentIds) ? documentIds : []) {
            uploadedIds.add(id);
        }
        showUploaded();
    });

    const uploadFiles = async ({ files, accessToken, context }) => {
        const selectedFolderId = env.searchModel.getSelectedFolderId();
        // All and Recent hold no files of their own: an upload there lands in My Drive
        const selectedUserFolderId = [false, UserFolder.RECENT].includes(
            selectedFolderId,
        )
            ? UserFolder.MY
            : selectedFolderId;
        const uploadContext = WRITABLE_ROOTS.includes(selectedUserFolderId)
            ? { ...context, default_user_folder_id: selectedUserFolderId }
            : context;
        await documentService.uploadDocument(files, accessToken, uploadContext, {
            targetFolderId: selectedUserFolderId,
        });
    };

    useBus(bus, DocumentsViewEvent.UPLOAD_FILES, (ev) => {
        component.uploadFiles({
            ...ev.detail,
            context: {
                ...component.props.context,
                ...ev.detail.context,
            },
        });
    });

    return {
        uploadFiles,
        onFileInputChange: async (ev) => {
            if (!ev.target.files.length) {
                return;
            }
            await component.uploadFiles({
                files: ev.target.files,
                accessToken: documentService.currentFolderAccessToken,
                context: component.props.context,
            });
            ev.target.value = "";
        },
    };
}
