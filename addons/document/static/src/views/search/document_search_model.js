/** @odoo-module native */
import {
    FOLDER_STORAGE_KEY,
    isSpecialFolderId,
    SEARCH_PANEL_UPDATED,
    toFolderValueId,
    UserFolder,
} from "@document/views/utils";
import { useSetupAction } from "@web/core/action_hook";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";
import { RpcEvent } from "@web/core/events";
import { rpcBus } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { SearchModel } from "@web/search/search_model";

const log = makeLogger("document.search");

export class DocumentsSearchModel extends SearchModel {
    setup(services) {
        super.setup(services);
        this.documentService = useService("document.document");
        this.orm = useService("orm");
        useSetupAction({
            beforeLeave: () => {
                this._updateRouteState({ user_folder_id: undefined });
            },
        });
    }

    /**
     * @returns {Object|undefined}
     */
    get folderCategory() {
        return this.categories.find((cat) => cat.fieldName === "user_folder_id");
    }

    async load(config) {
        const { documents_init_document_id: documentId, documents_view_secondary } =
            config.context;
        delete config.context.documents_init_document_id;
        if (!documents_view_secondary) {
            if (documentId) {
                this.documentService.requestFocus(documentId);
            }
            // the document asked for is shown whatever the defaults would filter
            if (this.documentService.focusRequest) {
                // a search model loaded without saved filters has none to disarm
                for (const irFilter of config.irFilters || []) {
                    irFilter.is_default = false;
                }
                for (const key in config.context) {
                    if (key.startsWith("search_default_")) {
                        delete config.context[key];
                    }
                }
            }
        }

        await super.load(config);

        let folderId = router.current.user_folder_id || this.getSelectedFolderId();
        const reachable = Boolean(folderId && this.getFolderById(folderId));
        log.logic("load", () => ({ folderId, reachable }));

        if (folderId) {
            if (!reachable) {
                folderId = false;
            }
            this.toggleCategoryValue(this.folderCategory.id, folderId);
        }
    }

    /**
     * @override
     */
    _createCategoryTree(sectionId) {
        const category = this.sections.get(sectionId);
        super._createCategoryTree(...arguments);
        const findRootId = (folder) => {
            if (!folder.parentId) {
                return folder.id;
            }
            const parent = category.values.get(folder.parentId);
            if (!parent) {
                return false;
            }
            if (parent.rootId !== undefined) {
                return parent.rootId;
            } else {
                const rootId = findRootId(parent);
                parent.rootId = rootId;
                return rootId;
            }
        };
        for (const [, folder] of category.values) {
            if (!folder.rootId) {
                folder.rootId = findRootId(folder);
            }
        }
    }

    /**
     * @override
     */
    takeSearchDefaultsFromGlobalContext() {
        const { searchDefaults, searchPanelDefaults } =
            super.takeSearchDefaultsFromGlobalContext(...arguments);
        if (searchPanelDefaults.user_folder_id) {
            searchPanelDefaults.user_folder_id = toFolderValueId(
                searchPanelDefaults.user_folder_id,
            );
            if (!this.globalContext.no_documents_unique_folder_id) {
                this.globalContext["documents_unique_folder_id"] =
                    searchPanelDefaults.user_folder_id;
            }
        }
        return { searchDefaults, searchPanelDefaults };
    }

    /**
     * @returns {Object[]}
     */
    getFolders() {
        return [...(this.folderCategory?.values.values() ?? [])];
    }

    /**
     * @returns {Object | false}
     */
    getFolderById(folderId) {
        return this.folderCategory?.values.get(folderId) || false;
    }

    /**
     * @returns {number | string | false}
     */
    getSelectedFolderId() {
        return this.folderCategory?.activeValueId ?? false;
    }

    /**
     * @returns {Object | false}
     */
    getSelectedFolder() {
        return this.getFolderById(this.getSelectedFolderId());
    }

    /**
     * @returns {Object[]}
     */
    getFolderAndParents(folder) {
        const folders = [];
        while (folder) {
            folders.push(folder);
            folder = this.getFolderById(folder.user_folder_id);
        }
        return folders;
    }

    /**
     * @returns {Object[]}
     */
    getSelectedFolderAndParents() {
        return this.getFolderAndParents(
            this.getFolderById(this.getSelectedFolderId() || false),
        );
    }

    /**
     * @override
     */
    toggleCategoryValue(sectionId, valueId) {
        const result = super.toggleCategoryValue(...arguments);
        const secondary = Boolean(this.context.documents_view_secondary);
        log.logic("toggleCategoryValue", () => ({ sectionId, valueId, secondary }));

        const selectedFolder = this.getSelectedFolder();
        if (!secondary) {
            browser.localStorage.setItem(FOLDER_STORAGE_KEY, valueId);
            this.documentService.updateDocumentURL(selectedFolder);
        }
        if (typeof valueId === "number") {
            this.documentService.logAccess(selectedFolder.access_token, "folder");
        }
        return result;
    }

    async _reloadSearchModel(reloadCategories) {
        log.logic("reloadSearchModel", () => ({ reloadCategories }));
        if (reloadCategories) {
            await this._reloadSearchPanel(true);
        }
        await this._notify();
    }

    async _reloadSearchPanel(skipUpdate = false) {
        const end = log.perf("reloadSearchPanel");
        // called when the tree may have changed: its cached copy would be
        // served first and then replaced by the answer, notifying twice
        rpcBus.trigger(RpcEvent.CLEAR_CACHES, {
            tables: ["search_panel_select_range"],
            model: "document.document",
        });
        await this._fetchSections(
            this.getSections((s) => s.type === "category"),
            [],
        );
        end();
        if (!skipUpdate) {
            this.trigger(SEARCH_PANEL_UPDATED);
        }
    }

    /**
     * @override
     */
    _getCategoryDomain(excludedCategoryId) {
        const userFolderCategory = this.folderCategory;
        if (excludedCategoryId === userFolderCategory.id) {
            return super._getCategoryDomain(excludedCategoryId);
        }
        if (
            [UserFolder.COMPANY, UserFolder.MY, UserFolder.RECENT].includes(
                userFolderCategory.activeValueId,
            )
        ) {
            return [["user_folder_id", "=", userFolderCategory.activeValueId]];
        }
        if (userFolderCategory.activeValueId === UserFolder.TRASH) {
            return [["active", "=", false]];
        }
        if (userFolderCategory.activeValueId === UserFolder.SHARED) {
            return Domain.and([
                [["shortcut_document_id", "=", false]],
                [["user_folder_id", "=", UserFolder.SHARED]],
            ]).toList();
        }
        if (!userFolderCategory.activeValueId) {
            if (this.context.documents_unique_folder_id) {
                return [["id", "child_of", this.context.documents_unique_folder_id]];
            }
            return [];
        }
        const folder = this.getSelectedFolder();
        const folderIdToOpen = folder?.shortcut_document_id?.length
            ? folder.shortcut_document_id[0]
            : userFolderCategory.activeValueId;
        const result = super._getCategoryDomain();
        const folderLeafIdx = result.findIndex(
            (leaf) => leaf[0] === "user_folder_id" && leaf[1] === "=",
        );
        if (folderLeafIdx !== -1) {
            result.splice(folderLeafIdx, 1, ...[["folder_id", "=", folderIdToOpen]]);
        }
        return result;
    }

    /**
     * @override Force
     */
    get orderBy() {
        const activeFolderId = this.folderCategory?.activeValueId;
        if (activeFolderId === UserFolder.TRASH) {
            return [
                { name: "create_date", asc: false },
                { name: "is_folder", asc: true },
            ];
        }
        if (activeFolderId === UserFolder.RECENT) {
            return [
                { name: "is_folder", asc: false },
                { name: "last_access_date_group", asc: false },
                { name: "write_date", asc: false },
            ];
        }
        const orderBy = super.orderBy;
        if (!orderBy.length) {
            return [{ name: "create_date", asc: false }];
        }
        return orderBy;
    }

    get groupBy() {
        const groupBy = super.groupBy;
        if (
            !groupBy?.length &&
            this.folderCategory?.activeValueId === UserFolder.RECENT
        ) {
            return ["last_access_date_group"];
        }
        return groupBy;
    }

    /**
     * @param {Object} category
     * @param {number|string|false} valueId
     * @returns {boolean}
     */
    _isCategoryValueReachable(category, valueId) {
        const queue = [...category.rootIds];
        const seen = new Set();
        while (queue.length) {
            const folderId = queue.pop();
            if (seen.has(folderId)) {
                continue;
            }
            seen.add(folderId);
            const folder = category.values.get(folderId);
            if (!folder) {
                continue;
            }
            if (folder.id === valueId) {
                return true;
            }
            queue.push(...folder.childrenIds);
        }
        return false;
    }

    /**
     * @override
     */
    _updateCategoryValue(category, valueIds) {
        if (
            valueIds.includes(category.activeValueId) &&
            this._isCategoryValueReachable(category, category.activeValueId)
        ) {
            return;
        }
        if (this.context.documents_init_folder_id !== undefined) {
            category.activeValueId = this.context.documents_init_folder_id || false;
            return;
        }
        const storageItem = browser.localStorage.getItem(FOLDER_STORAGE_KEY);
        if (storageItem && !isSpecialFolderId(storageItem)) {
            try {
                category.activeValueId = JSON.parse(storageItem);
            } catch {
                category.activeValueId = false;
            }
        } else {
            category.activeValueId = storageItem;
        }
        // a special root counts only where this panel has it (none for a portal user)
        if (
            (isSpecialFolderId(category.activeValueId) &&
                category.values.has(category.activeValueId)) ||
            (valueIds.includes(category.activeValueId) &&
                this._isCategoryValueReachable(category, category.activeValueId))
        ) {
            return;
        }
        if (category.values.has(category.activeValueId)) {
            let newSection = category.values.get(
                category.values.get(category.activeValueId).parentId,
            );
            while (
                newSection &&
                !this._isCategoryValueReachable(category, newSection.id)
            ) {
                newSection = category.values.get(newSection.parentId);
            }
            if (newSection) {
                // the nearest ancestor still reachable; when that is "All"
                // (false: a portal user's roots), the tree's first folder
                category.activeValueId =
                    newSection.id || (valueIds.find((id) => id !== false) ?? false);
            } else {
                category.activeValueId = this.documentService.userIsInternal
                    ? UserFolder.COMPANY
                    : valueIds[0];
            }
            browser.localStorage.setItem(FOLDER_STORAGE_KEY, category.activeValueId);
        } else {
            category.activeValueId = false;
        }
    }

    /**
     * The first load waits: the folder it opens decides the records' domain.
     * A later search does not: the folder tree is expanded and never refetched,
     * and a filter section's values follow the records a moment later, while
     * the values already checked are in the domain the records are read with.
     *
     * @override
     */
    _shouldWaitForData() {
        return !this.searchPanelInfo.loaded;
    }

    _updateRouteState(state) {
        router.pushState(state);
    }
}
