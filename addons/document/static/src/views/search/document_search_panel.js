/** @odoo-module native */
import { useDocumentContext } from "@document/views/document_context";
import {
    DocumentsViewEvent,
    SEARCH_PANEL_UPDATED,
    specialFolderDropRefusal,
    toFolderValueId,
    UserFolder,
    WRITABLE_ROOTS,
} from "@document/views/utils";
import { onWillStart, proxy } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useNestedSortable } from "@web/core/utils/dnd";
import { useBus, useService } from "@web/core/utils/hooks";
import { useViewModel } from "@web/model/model";
import { useSearchModel } from "@web/search/search_model";
import { SearchPanel } from "@web/search/search_panel/search_panel";
import { utils as uiUtils } from "@web/ui/viewport";

export class DocumentsSearchPanel extends SearchPanel {
    static get template() {
        return !uiUtils.isSmall()
            ? "document.SearchPanel"
            : "document.SearchPanel.Small";
    }
    static subTemplates = {
        section: "web.SearchPanel.Section",
        category: "document.SearchPanel.Category",
        filtersGroup: "document.SearchPanel.FiltersGroup",
    };
    static rootIcons = {
        false: "fa-regular fa-folder",
        COMPANY: "fa-solid fa-building",
        MY: "fa-solid fa-hard-drive",
        RECENT: "fa-regular fa-clock",
        SHARED: "fa-solid fa-users",
        TRASH: "fa-solid fa-trash",
    };
    setup() {
        super.setup(...arguments);
        this.documentContext = useDocumentContext();
        this.searchModel = useSearchModel();
        this.model = useViewModel();
        const { uploads } = useService("file_upload");
        this.documentService = useService("document.document");
        this.documentUploads = proxy(uploads);
        this.notification = useService("notification");
        this.orm = useService("orm");

        onWillStart(async () => {
            await this.searchModel.sectionsPromise;
            if (this.model.config.context.active_model) {
                const categories = await this.searchModel.getSections(
                    (s) => s.type === "category",
                );
                for (const category of categories) {
                    this.state.expanded[category.id] = {};
                }
            } else {
                const selectedFolderId = await this.searchModel.getSelectedFolderId();
                if (selectedFolderId) {
                    this.state.expanded[this.sections[0].id][UserFolder.COMPANY] = true;
                    this._expandFolder({ folderId: selectedFolderId });
                }
            }
        });

        useBus(
            this.documentContext.documentsView.bus,
            DocumentsViewEvent.EXPAND_FOLDER,
            (ev) => {
                this._expandFolder(ev.detail);
            },
        );

        useBus(this.searchModel, SEARCH_PANEL_UPDATED, async () => {
            this.updateActiveValues();
            this.state.searchModelUpdates++;
        });

        useNestedSortable({
            ref: this.root,
            groups: ".o_search_panel_category",
            elements: "li:not(.o_all_or_trash_category)",
            enable: () => this.documentService.userIsInternal,
            nest: true,
            nestInterval: 10,
            /**
             * @param {HTMLElement} parent
             * @param {HTMLElement} newGroup
             * @param {{parent: HTMLElement}} prevPos
             * @param {HTMLElement} placeholder
             */
            onMove: ({ parent, newGroup, prevPos, placeholder }) => {
                if (parent) {
                    parent.classList.add("o_has_treeEntry");
                    placeholder.classList.add("o_treeEntry");
                    const parentSectionId = parseInt(newGroup.dataset.sectionId);
                    const parentValueId = parseInt(parent.dataset.valueId);
                    this.state.expanded[parentSectionId][parentValueId] = true;
                } else {
                    placeholder.classList.remove("o_treeEntry");
                }
                if (prevPos.parent && !prevPos.parent.querySelector("li")) {
                    prevPos.parent.classList.remove("o_has_treeEntry");
                }
            },
            onDrop: (params) => this.onFolderDrop(params),
        });
    }

    /**
     * A folder dropped in the tree: moved under its new parent, before `next`.
     * Into My Drive from elsewhere it is linked, not moved: a shortcut.
     *
     * @param {{element: HTMLElement, parent?: HTMLElement, next?: HTMLElement}} params
     */
    async onFolderDrop({ element, parent, next }) {
        const draggingFolderId = toFolderValueId(element.dataset.valueId);
        const parentFolderId = parent ? toFolderValueId(parent.dataset.valueId) : false;
        // a root entry (MY, COMPANY) holds no sequence to sort against
        const nextId = next ? toFolderValueId(next.dataset.valueId) : false;
        const beforeFolderId = typeof nextId === "number" ? nextId : false;
        if (
            typeof draggingFolderId !== "number" ||
            !parentFolderId ||
            draggingFolderId === parentFolderId ||
            this._notifyWrongDropDestination(parentFolderId)
        ) {
            return;
        }
        // the company root takes folders from managers only; a folder under
        // it is judged by its own permission, server side
        if (
            parentFolderId === UserFolder.COMPANY &&
            !this.documentService.userIsDocumentManager
        ) {
            this.notification.add(
                _t("Only Documents Managers can create in company folder."),
                { type: "warning" },
            );
            return;
        }
        const parentFolder = this.searchModel.getFolderById(parentFolderId);
        const draggingFolder = this.searchModel.getFolderById(draggingFolderId);
        if (
            parentFolder.rootId === UserFolder.MY &&
            draggingFolder.rootId !== UserFolder.MY
        ) {
            await this.orm.call(
                "document.document",
                "action_create_shortcut",
                [draggingFolderId],
                { location_user_folder_id: String(parentFolderId) },
            );
            await this.searchModel._reloadSearchModel(true);
            return;
        }
        const moved = await this.documentService.moveConfirmingAccess(
            (context) =>
                this.orm.call(
                    "document.document",
                    "action_move_folder",
                    [[draggingFolderId], String(parentFolderId), beforeFolderId],
                    { context },
                ),
            parentFolder.display_name,
        );
        if (moved) {
            await this.searchModel._reloadSearchModel(true);
        }
    }

    /**
     * @param {number|String} folderId
     * @returns {boolean}
     */
    isUploadingInFolder(folderId) {
        return Object.values(this.documentUploads).some(
            (upload) => upload.targetFolderId === folderId,
        );
    }

    /**
     * @param {Object} category
     * @param {Object} value
     */
    async toggleCategory(category, value) {
        if (!value.childrenIds.length) {
            this.getDropdownState(category.id).close();
        }
        if (category.activeValueId !== value.id) {
            const folder = this.searchModel.getFolderById(value.id);
            const isShortcut = !!folder.shortcut_document_id?.length;
            if (
                isShortcut &&
                !this.searchModel.getFolderById(folder.shortcut_document_id[0])
            ) {
                // the target left the tree: trashed, where there is a trash to
                // show, else out of this panel's scope
                if (this.searchModel.getFolderById(UserFolder.TRASH)) {
                    return this.searchModel.toggleCategoryValue(
                        category.id,
                        UserFolder.TRASH,
                    );
                }
                return this.notification.add(
                    _t("The folder this shortcut points to is not available here."),
                    { type: "warning" },
                );
            }
            this.searchModel.toggleCategoryValue(category.id, value.id);
        }
    }

    /**
     * @param {*} category
     * @param {*} value
     */
    async toggleFold(category, value) {
        const categoryState = this.state.expanded[category.id];
        categoryState[value.id] = !categoryState[value.id];
    }

    /**
     * @param {Object} param0
     * @param {number|String} param0.folderId
     */
    _expandFolder({ folderId }) {
        const sectionId = this.sections[0].id;
        const folders = this.searchModel.getFolderAndParents(
            this.searchModel.getFolderById(folderId),
        );
        if (!folders.length) {
            return;
        }
        if (
            folders[0].id === UserFolder.COMPANY ||
            this.state.expanded[sectionId][folders[0].rootId]
        ) {
            for (const folder of folders) {
                this.state.expanded[sectionId][folder.id] = true;
            }
        }
    }

    /**
     * @param {number|String} folderId
     * @returns {boolean} whether the destination was refused (and said so)
     */
    _notifyWrongDropDestination(folderId) {
        if (typeof folderId !== "number" && !WRITABLE_ROOTS.includes(folderId)) {
            this.notification.add(specialFolderDropRefusal(), {
                title: _t("Invalid operation"),
                type: "warning",
            });
            return true;
        }
        return false;
    }
}
