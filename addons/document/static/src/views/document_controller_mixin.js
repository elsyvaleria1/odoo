/** @odoo-module native */
import { rememberDocumentsViewType } from "@document/core/document_client_action";
import { isDownloadAllowed } from "@document/views/document_actions";
import {
    DOCUMENTS_VIEW_REQUIRED_FIELDS,
    preSuperSetup,
    useDocumentView,
} from "@document/views/hooks";
import { getCommonEmbeddedActions } from "@document/views/utils";
import { onWillDestroy, proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewConfig } from "@web/core/view_config_hooks";
import { makeActiveField } from "@web/model/relational_model";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { useSearchModel } from "@web/search/search_model";
import { prepareStaticActionMenuItems } from "@web/views/view_utils";

const log = makeLogger("document.controller");

/**
 * Whether the selection's actions show: not over a preview, and not while the
 * details panel shows a document outside the selection.
 *
 * @param {{ previewedDocument: Object|null, focusedRecord: Object|null }} rightPanelState
 * @param {Object[]} selection
 * @returns {boolean}
 */
export function showsSelectionActions({ previewedDocument, focusedRecord }, selection) {
    if (previewedDocument) {
        return false;
    }
    return !focusedRecord || selection.some((record) => record.id === focusedRecord.id);
}

export const DocumentsControllerMixin = (component) =>
    class extends component {
        /** Whether this view carries the selection's action menus. */
        static hasSelectionActions = true;

        setup() {
            preSuperSetup();
            super.setup(...arguments);
            this.ui = useService("ui");
            this.searchModel = useSearchModel();

            this.documentService = useService("document.document");
            this.uploadFileInputRef = elementRef();
            Object.assign(this, useDocumentView(this, this.documentsViewHelpers()));
            this.documentStates = proxy({ previewStore: {} });
            this.rightPanelState = proxy(this.documentService.rightPanelReactive);

            // a picker opened in a dialog must not take the menus of the view below
            const providesActions =
                this.constructor.hasSelectionActions &&
                !this.searchModel.context.documents_view_secondary;
            log.lifecycle("setup", () => ({
                controller: this.constructor.name,
                providesActions,
            }));
            if (providesActions) {
                this.provideSelectionActions();
            }

            useLayoutEffect(() => this.openInitialPreview());

            // the Documents app reopens on the layout last chosen on a large screen
            const viewConfig = useViewConfig();
            if (
                viewConfig.actionXmlId === "document.document_action" &&
                ["kanban", "list"].includes(viewConfig.viewType) &&
                !this.ui.isSmall
            ) {
                rememberDocumentsViewType(viewConfig.viewType);
            }
        }

        provideSelectionActions() {
            // Registered synchronously: the control panel's DocumentsAction reads
            // it from its own mounted effect, which runs before this component's.
            const provider = () => ({
                getTopbarActions: () => this.getTopBarActionMenuItems(),
                getMenuProps: () => this.actionMenuProps,
            });
            this.documentService.selectionActions.provider = provider;
            onWillDestroy(() => {
                // On a view switch the next controller has already registered its own.
                if (this.documentService.selectionActions.provider === provider) {
                    this.documentService.selectionActions.provider = null;
                }
            });
        }

        get hasSelectedRecords() {
            return this.targetRecords.length > 0;
        }

        get targetRecords() {
            return this.model.targetRecords;
        }

        /**
         * Opens the preview (or the PDF splitter) the bus asks for. A method,
         * so that a bridge can preview some documents its own way.
         *
         * @param {Object} detail what `documents-open-preview` carries
         */
        onOpenDocumentsPreview(detail) {
            return this.documentsPreview.open(detail);
        }

        documentsViewHelpers() {
            return {
                setPreviewStore: (previewStore) => {
                    this.documentStates.previewStore = previewStore;
                },
                isRecordPreviewable: this.isRecordPreviewable.bind(this),
            };
        }

        isRecordPreviewable(record) {
            return record.isViewable();
        }

        openInitialPreview() {
            const documentId = this.model.pendingPreviewId;
            const doc =
                documentId &&
                this.model.root.records.find((r) => r.resId === documentId);
            log.logic("openInitialPreview", () => ({
                documentId,
                found: Boolean(doc),
            }));
            if (!doc) {
                return;
            }
            this.model.pendingPreviewId = undefined;
            // a file the viewer cannot show (an archive) stays selected only
            if (doc.isViewable()) {
                doc.openPreview();
            }
        }

        get modelParams() {
            const modelParams = super.modelParams;
            modelParams.multiEdit = true;
            const sharedSelection = this.props.globalState?.sharedSelection;
            if (sharedSelection) {
                modelParams.state = { ...modelParams.state, sharedSelection };
            }

            const activeFields = Object.keys(modelParams.config.activeFields);

            DOCUMENTS_VIEW_REQUIRED_FIELDS.forEach((field) => {
                if (!activeFields.includes(field)) {
                    modelParams.config.activeFields[field] = makeActiveField();
                }
            });

            if (!activeFields.includes("res_id")) {
                modelParams.config.activeFields.res_id = makeActiveField();
                modelParams.config.activeFields.res_id.related = {
                    fields: {
                        display_name: {
                            name: "display_name",
                            type: "char",
                        },
                    },
                    activeFields: {
                        display_name: makeActiveField(),
                    },
                };
            }

            if (!activeFields.includes("tag_ids")) {
                modelParams.config.activeFields.tag_ids = makeActiveField();
                modelParams.config.activeFields.tag_ids.related = {
                    activeFields: {
                        display_name: makeActiveField({ readonly: true }),
                        color: makeActiveField(),
                    },
                    fields: {
                        display_name: {
                            name: "display_name",
                            type: "char",
                            readonly: true,
                        },
                        color: {
                            name: "color",
                            type: "integer",
                            readonly: false,
                        },
                    },
                };
            }

            if (!activeFields.includes("alias_tag_ids")) {
                modelParams.config.activeFields.alias_tag_ids = {
                    ...modelParams.config.activeFields.tag_ids,
                };
            }

            return modelParams;
        }

        getEmbeddedActions() {
            const embeddedActions = getCommonEmbeddedActions(this.model.targetRecords);
            // an integer key would put the folder's actions in id order, not the
            // order the server sequenced them in
            return Object.fromEntries(
                embeddedActions.map((e) => [
                    `embedded_action_${e.id}`,
                    {
                        description: e.name,
                        callback: () => this.model.onDoAction(e.id),
                        groupNumber: COG_GROUP.ACTIONS,
                    },
                ]),
            );
        }

        getTopBarActionMenuItems() {
            const embeddedActions = this.getEmbeddedActions();
            const userIsInternal = this.documentService.userIsInternal;
            return {
                ...embeddedActions,
                download: {
                    isAvailable: () =>
                        this.targetRecords.some(
                            (r) => !r.isRequest() && isDownloadAllowed(r.data),
                        ),
                    sequence: 10,
                    description: _t("Download"),
                    icon: "fa-solid fa-download",
                    callback: () => this.model.onDownload(),
                    groupNumber: COG_GROUP.DATA,
                },
                share: {
                    isAvailable: () => userIsInternal && this.targetRecords.length > 0,
                    sequence: 10,
                    description: _t("Share…"),
                    icon: "fa-solid fa-share-nodes",
                    callback: () => this.model.onShare(),
                    groupNumber: COG_GROUP.RECORD,
                },
            };
        }

        getStaticActionMenuItems() {
            const selectionCount = this.targetRecords.length;
            const userIsInternal = this.documentService.userIsInternal;
            const singleSelection = selectionCount === 1 && this.targetRecords[0];
            const isInTrash = this.searchModel.getSelectedFolderId() === "TRASH";
            const editMode = this.targetRecords.every(
                (r) => r.data.user_permission === "edit",
            );
            const someArchived = this.targetRecords.some((r) => !r.data.active);
            const menuItems = super.getStaticActionMenuItems();
            const topBarActions = this.ui.isSmall
                ? this.getTopBarActionMenuItems()
                : {};
            return {
                ...omit(menuItems, "archive", "delete", "duplicate", "unarchive"),
                ...topBarActions,
                ...prepareStaticActionMenuItems({
                    duplicate: {
                        isAvailable: () => this.model.canDuplicateRecords,
                        callback: () => this.model.onDuplicate(),
                    },
                    delete: {
                        isAvailable: () => this.model.canDeleteRecords,
                        callback: () => this.model.onDelete(),
                    },
                }),
                copy: {
                    isAvailable: () => selectionCount && !isInTrash,
                    sequence: 30,
                    description: _t("Copy Links"),
                    icon: "fa-solid fa-link",
                    callback: () => this.model.onCopyLinks(),
                    groupNumber: COG_GROUP.DATA,
                },
                rename: {
                    isAvailable: () =>
                        editMode &&
                        singleSelection &&
                        !this.model.isLockedByOther(singleSelection.data) &&
                        !isInTrash,
                    sequence: 20,
                    description: _t("Rename…"),
                    icon: "fa-regular fa-pen-to-square",
                    callback: () => this.model.onRename(),
                    groupNumber: COG_GROUP.RECORD,
                },
                move: {
                    isAvailable: () => this.model.canMoveRecords,
                    sequence: 25,
                    description: _t("Move…"),
                    icon: "fa-solid fa-right-to-bracket",
                    callback: () => this.model.onMove(),
                    groupNumber: COG_GROUP.RECORD,
                },
                shortcut: {
                    isAvailable: () => userIsInternal && !isInTrash,
                    sequence: 35,
                    description: _t("Add Shortcut…"),
                    icon: "fa-solid fa-up-right-from-square",
                    callback: () => this.model.onCreateShortcut(),
                    groupNumber: COG_GROUP.RECORD,
                },
                details: {
                    isAvailable: () =>
                        userIsInternal &&
                        !this.searchModel.context.documents_view_secondary,
                    sequence: 50,
                    description: _t("Info & Tags"),
                    icon: "fa-solid fa-circle-info",
                    callback: () => this.model.onToggleRightPanel(),
                    groupNumber: COG_GROUP.RECORD,
                },
                version: {
                    isAvailable: () => this.model.canManageVersions,
                    sequence: 55,
                    description: _t("Manage Versions…"),
                    icon: "fa-solid fa-clock-rotate-left",
                    callback: () => this.model.onManageVersions(),
                    groupNumber: COG_GROUP.RECORD,
                },
                trash: {
                    isAvailable: () => this.model.canArchiveRecords,
                    sequence: 80,
                    description: _t("Move to Trash"),
                    icon: "fa-regular fa-trash-can",
                    callback: () => this.model.onArchive(),
                    groupNumber: COG_GROUP.RECORD,
                },
                restore: {
                    isAvailable: () => someArchived,
                    sequence: 85,
                    description: _t("Restore"),
                    icon: "fa-solid fa-trash-arrow-up",
                    callback: () => this.model.onRestore(),
                    groupNumber: COG_GROUP.RECORD,
                },
                lock: {
                    isAvailable: () =>
                        userIsInternal &&
                        singleSelection &&
                        singleSelection.data.type !== "folder" &&
                        !isInTrash &&
                        editMode,
                    sequence: 45,
                    description: singleSelection?.data?.lock_uid
                        ? _t("Unlock")
                        : _t("Lock"),
                    icon: singleSelection?.data?.lock_uid
                        ? "fa-solid fa-lock-open"
                        : "fa-solid fa-lock",
                    callback: () => this.model.onToggleLock(),
                    groupNumber: COG_GROUP.RECORD,
                },
                pdf: {
                    isAvailable: () =>
                        userIsInternal &&
                        selectionCount &&
                        editMode &&
                        this.targetRecords.every(
                            (record) =>
                                record.isPdf() &&
                                !this.model.isLockedByOther(record.data),
                        ) &&
                        !isInTrash,
                    sequence: 10,
                    description: singleSelection ? _t("Split PDF…") : _t("Merge PDFs…"),
                    icon: "fa-solid fa-scissors",
                    callback: () => this.model.onSplitPDF(),
                    groupNumber: COG_GROUP.APP,
                },
            };
        }

        get showActions() {
            return showsSelectionActions(this.rightPanelState, this.targetRecords);
        }
    };
