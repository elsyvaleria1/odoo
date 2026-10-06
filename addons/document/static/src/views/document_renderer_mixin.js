/** @odoo-module native */
import { DocumentsBusEvent } from "@document/core/document_service";
import { useDraggableDocuments } from "@document/views/helper/document_draggable";
import { onMounted, onWillUpdateProps, proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useMountedListener, useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useViewModel } from "@web/model/model";
import {
    preprocessMany2oneChanges,
    preprocessMany2OneReferenceChanges,
    preprocessReferenceChanges,
    preprocessX2manyChanges,
} from "@web/model/relational_model";
import { useSearchModel } from "@web/search/search_model";
import { useCommand } from "@web/ui/commands";

const log = makeLogger("document.renderer");

const containerRecordClasses = new WeakMap();

/**
 * The current folder as a record, for the details panel: a search panel value,
 * not a row of the view. An edit is written at once, alone, and its reload is
 * the folder tree's (`reloadFolder`, set by the renderer making it).
 *
 * @param {typeof import("@web/model/relational_model").RelationalModel.Record} Record
 */
function containerRecordClass(Record) {
    if (!containerRecordClasses.has(Record)) {
        containerRecordClasses.set(
            Record,
            class DocumentsContainerRecord extends Record {
                isContainer = true;

                async updateLocked(changes) {
                    this.dirty = true;
                    const fieldsToSave = new Set(Object.keys(changes));
                    await Promise.all([
                        preprocessMany2oneChanges(this, changes),
                        preprocessMany2OneReferenceChanges(this, changes),
                        preprocessReferenceChanges(this, changes),
                        preprocessX2manyChanges(this, changes),
                    ]);
                    this.applyChanges(changes);
                    const changesToSave = Object.fromEntries(
                        Object.entries(this.getChangesLocked()).filter(([name]) =>
                            fieldsToSave.has(name),
                        ),
                    );
                    await this.model.orm.write(
                        "document.document",
                        [this.data.id],
                        changesToSave,
                    );
                    this.dirty = false;
                }

                async load() {
                    await this.reloadFolder?.();
                }

                async saveLocked() {
                    return true;
                }
            },
        );
    }
    return containerRecordClasses.get(Record);
}

export const DocumentsRendererMixin = (component) =>
    class extends component {
        /** The element standing for one record, and the one to focus after select-all. */
        static recordSelector = null;
        static focusSelector = (resId) => `[data-value-id="${resId}"]`;
        /** Where a dragged document may be dropped, and the classes marking the hover. */
        static dropTargetSelector = null;
        static dropHoverClasses = { hover: "o_drag_hover", invalid: "o_drag_invalid" };

        getDocumentsAttachmentViewerProps() {
            return { previewStore: this.props.previewStore };
        }

        setup() {
            super.setup();
            this.searchModel = useSearchModel();
            this.config = useViewConfig();
            this.model = useViewModel();
            // list and kanban bind their inherited rootRef, activity its own root
            this.root = this.rootRef ?? elementRef();
            this.documentService = useService("document.document");
            this.notificationService = useService("notification");
            const { uploads } = useService("file_upload");
            this.documentUploads = proxy(uploads);

            useCommand(
                _t("Select all"),
                () => {
                    const records = this.records;
                    const allSelected = this.selection.length === records.length;
                    log.logic("selectAll", () => ({
                        records: records.length,
                        unselect: allSelected,
                    }));
                    records.forEach((record) => {
                        record.toggleSelection(!allSelected);
                    });
                    const focusedRecord = this.setDefaultFocus();
                    this.root.el
                        ?.querySelector(
                            this.constructor.focusSelector(focusedRecord?.resId),
                        )
                        ?.focus();
                },
                {
                    category: "smart_action",
                    hotkey: "control+a",
                    isAvailable: () => this.records.length > 0,
                },
            );

            if (this.constructor.recordSelector) {
                const { hover, invalid } = this.constructor.dropHoverClasses;
                useDraggableDocuments({
                    ref: this.root,
                    model: this.model,
                    targetSelector: this.constructor.dropTargetSelector,
                    elements: this.constructor.recordSelector,
                    preventDrag: () =>
                        this.searchModel.getSelectedFolderId() === "TRASH" ||
                        this.refusesDomainDrag(),
                    onTargetPointerEnter: ({ addClass, target, isInvalid }) => {
                        addClass(target, isInvalid ? invalid : hover);
                    },
                    onTargetPointerLeave: ({ removeClass, target }) => {
                        removeClass(target, invalid, hover);
                    },
                });
            }

            // not in setup: the controller reads the focused record, and a
            // restart of its render re-creates this renderer, whose new focus
            // would restart it again
            onMounted(() =>
                this.documentService.focusRecord(
                    this.selection?.[0] || this.getContainerRecord(),
                    true,
                ),
            );
            this.rightPanelState = proxy(this.documentService.rightPanelReactive);

            useCommand(_t("Move to trash"), () => this.model.onArchive(), {
                category: "smart_action",
                hotkey: "control+m",
                isAvailable: () => this.model.canArchiveRecords,
            });
            useCommand(
                _t("Toggle favorite"),
                () => this.model.toggleFavorite(this.selection),
                {
                    category: "smart_action",
                    hotkey: "alt+t",
                    isAvailable: () => this.selection.length > 0,
                },
            );
            useCommand(_t("Delete"), () => this.model.onDelete(), {
                category: "smart_action",
                hotkey: "control+d",
                isAvailable: () => this.model.canDeleteRecords,
            });

            const setShortcutModifier = (active) => {
                this.root?.el?.classList.toggle("o_documents_dnd_shortcut", active);
            };
            useMountedListener(window, "keydown", (ev) => {
                if (ev.key === "Control") {
                    setShortcutModifier(true);
                }
            });
            useMountedListener(window, "keyup", (ev) => {
                if (ev.key === "Control") {
                    setShortcutModifier(false);
                }
            });
            useMountedListener(window, "blur", () => setShortcutModifier(false));

            // list and kanban get a new list per load, activity a new records array
            onWillUpdateProps((nextProps) => {
                if (
                    (nextProps.list ?? nextProps.records) !==
                    (this.props.list ?? this.props.records)
                ) {
                    const selection = nextProps.list
                        ? nextProps.list.selection
                        : nextProps.records.filter((r) => r.selected);
                    this.documentService.focusRecord(
                        selection?.[0] || this.getContainerRecord(),
                    );
                }
            });
            useBus(this.documentService.bus, DocumentsBusEvent.FOCUS_FOLDER, () => {
                this.documentService.focusRecord(this.getContainerRecord());
            });
        }
        setDefaultFocus() {
            const focusedRecord = this.documentService.focusedRecord;
            const records = this.records;
            if (!focusedRecord || !records.find((r) => r.id === focusedRecord.id)) {
                const record =
                    this.config.viewType === "kanban"
                        ? records.find((r) => r.data.type === "folder") || records[0]
                        : records[0];
                this.documentService.focusRecord(
                    record || this.getContainerRecord(),
                    true,
                );
            }
            return this.documentService.focusedRecord;
        }
        /**
         * The current folder as a record, for the details panel. One per folder
         * value (the search model replaces them on reload) and size, so
         * focusing it again is recognised as the same focus.
         */
        getContainerRecord() {
            const folder = this.searchModel.getSelectedFolder();
            const fileSize = this.props.list?.model.fileSize || 0;
            const cached = this._containerRecord;
            const hit = cached?.folder === folder && cached.fileSize === fileSize;
            log.logic("containerRecord", () => ({ folderId: folder?.id, reused: hit }));
            if (hit) {
                return cached.record;
            }
            const record = this._makeContainerRecord(folder, fileSize);
            this._containerRecord = { folder, fileSize, record };
            return record;
        }

        _makeContainerRecord(folder, fileSize) {
            const folderData = this.searchModel.getFolderAndParents(folder);
            // a panel value has no folder_id: its parent is the next one up
            const folderId =
                folderData?.length > 1 && typeof folderData[1].id === "number"
                    ? [folderData[1].id, folderData[1].display_name]
                    : false;

            const data = Object.assign({}, folder, {
                folder_id: folderId,
                name: folder.display_name,
                type: "folder",
                file_size: fileSize,
            });
            const config = { ...this.model.config, resId: data.id };
            const ContainerRecord = containerRecordClass(this.model.constructor.Record);
            const record = new ContainerRecord(this.model, config, data);
            record.reloadFolder = async () => {
                await this.searchModel._reloadSearchPanel();
                this.documentService.focusRecord(this.getContainerRecord());
            };
            return record;
        }

        /**
         * Whether a drag is refused for the whole domain being selected,
         * which the user is told: only the page's documents are on screen.
         *
         * @returns {boolean}
         */
        refusesDomainDrag() {
            if (this.model.isDomainSelected) {
                this.notificationService.add(
                    _t("Only current page items can be dragged."),
                    {
                        type: "info",
                    },
                );
            }
            return this.model.isDomainSelected;
        }

        getNbViewItems() {
            return this.props.list?.count ?? this.records.length;
        }

        /** list and kanban render a `list`, activity its flat `records` */
        get records() {
            return this.props.list?.records ?? this.props.records;
        }

        get selection() {
            return this.props.list?.selection ?? this.records.filter((r) => r.selected);
        }
    };
