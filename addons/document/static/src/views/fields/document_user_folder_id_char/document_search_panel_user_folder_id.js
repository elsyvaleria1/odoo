/** @odoo-module native */
import { DocumentsSearchPanel } from "@document/views/search/document_search_panel";
import { toFolderValueId } from "@document/views/utils";
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { isActivationKey } from "@web/core/browser/hotkeys";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { fuzzyTest } from "@web/core/utils/search";

export class DocumentsSearchPanelUserFolderId extends Component {
    static excludedValues = ["RECENT", "TRASH"];
    static template = "document.SearchPanelUserFolderId";
    static subTemplates = {
        category: "document.SearchPanel.Category",
    };
    static rootIcons = DocumentsSearchPanel.rootIcons;
    static props = {
        value: t.string(),
        onChange: t.function(),
        ulClass: t.string().optional(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.ui = useService("ui");
        this.orm = useService("orm");
        const activeValueId = toFolderValueId(this.props.value);
        this.state = proxy({ expanded: { 1: {} } });
        this.category = proxy({
            activeValueId,
            description: "Folders",
            icon: "fa-folder",
            id: 1,
            rootIds: [],
            values: new Map(),
        });
        this._treeValues = [];
        this.inputRef = elementRef();

        onWillStart(async () => {
            const result = await this.orm.call(
                "document.document",
                "search_panel_select_range",
                ["user_folder_id"],
                {},
            );
            const values = result.values
                .filter((v) => !this.constructor.excludedValues.includes(v.id))
                .sort((a, b) => (a.id === "MY" ? -1 : b.id === "MY" ? 1 : 0));
            this._treeValues = values;
            this._createCategoryTree({ values, initialValue: activeValueId });
        });
    }

    get ulClass() {
        return this.props.ulClass || "";
    }

    isUploadingInFolder() {
        return false;
    }

    async toggleCategory(category, value) {
        // shared folders are listed under it, but nothing is moved into it
        if (value.id === "SHARED") {
            return this.toggleFold(category, value);
        }
        const newActiveValueId = value.id;
        if (category.activeValueId !== newActiveValueId) {
            this.props.onChange(newActiveValueId.toString(), value);
            category.activeValueId = newActiveValueId;
        }
    }

    /** The shared category template binds it on every folder header. */
    onCategoryKeydown(ev, category, value) {
        if (!isActivationKey(ev)) {
            return;
        }
        ev.preventDefault();
        this.toggleCategory(category, value);
    }

    async toggleFold(category, value) {
        const categoryState = this.state.expanded[category.id];
        categoryState[value.id] = !categoryState[value.id];
    }

    /**
     * @param {Object} category
     * @param {Object} value
     * @returns {string|false}
     */
    categoryAriaExpanded(category, value) {
        if (!value.childrenIds.length) {
            return false;
        }
        return this.state.expanded[category.id][value.id] ? "true" : "false";
    }

    onFilterInput(ev) {
        this._filter(ev.target.value);
    }

    onClickClear() {
        this.inputRef.el.value = "";
        this._filter("");
    }

    /** @param {string} query */
    _filter(query) {
        this._createCategoryTree({
            values: this._treeValues,
            query,
            initialValue: this.category.activeValueId,
        });
    }

    /**
     * @param { Object[] } values
     * @param { String? } query
     * @param { Number } initialValue
     */
    _createCategoryTree({ values, query, initialValue }) {
        const category = this.category;
        const lowercaseQuery = query?.toLowerCase();
        const newCategoryValues = new Map();
        for (const value of values) {
            const parentId = value["user_folder_id"] || false;
            newCategoryValues.set(
                value.id,
                Object.assign({}, value, {
                    parentId,
                    childrenIds: [],
                }),
            );
        }

        for (const [id, node] of newCategoryValues.entries()) {
            const parentId = node.parentId;
            if (parentId && newCategoryValues.has(parentId)) {
                newCategoryValues.get(parentId).childrenIds.push(id);
            }
        }

        let idsToInclude = new Set(newCategoryValues.keys());
        const newExpanded = {};

        if (lowercaseQuery) {
            const matchingIds = new Set();
            for (const [id, node] of newCategoryValues.entries()) {
                if (!node.parentId) {
                    continue;
                }
                if (node.display_name && fuzzyTest(lowercaseQuery, node.display_name)) {
                    matchingIds.add(id);
                }
            }

            const relevantIds = new Set(matchingIds);

            for (const id of matchingIds) {
                let current = newCategoryValues.get(id);
                while (current?.parentId && newCategoryValues.has(current.parentId)) {
                    const parentId = current.parentId;
                    relevantIds.add(parentId);
                    newExpanded[parentId] = true;
                    current = newCategoryValues.get(parentId);
                }
            }

            const collectDescendants = (id) => {
                const node = newCategoryValues.get(id);
                if (!node) {
                    return;
                }
                for (const childId of node.childrenIds) {
                    if (!relevantIds.has(childId)) {
                        relevantIds.add(childId);
                        collectDescendants(childId);
                    }
                }
            };
            for (const id of matchingIds) {
                collectDescendants(id);
            }

            for (const [id, node] of newCategoryValues.entries()) {
                if (!node.parentId) {
                    relevantIds.add(id);
                }
            }
            idsToInclude = relevantIds;
        } else {
            for (const [id, node] of newCategoryValues.entries()) {
                if (!node.parentId) {
                    newExpanded[id] = true;
                }
            }
            const ancestors = this.getFolderAndParents(newCategoryValues, initialValue);
            for (const folder of ancestors) {
                if (!newExpanded[folder.id]) {
                    newExpanded[folder.id] = true;
                }
            }
        }

        this.state.expanded[1] = newExpanded;

        this._setCategoryValues(category, idsToInclude, newCategoryValues);

        category.rootIds = [];
        for (const [id, node] of category.values.entries()) {
            if (!node.parentId || !category.values.has(node.parentId)) {
                category.rootIds.push(id);
            }
        }
    }

    /** The values kept, each with the children kept among its own. */
    _setCategoryValues(category, idsToInclude, categoryMap) {
        category.values.clear();
        for (const [id, node] of categoryMap) {
            if (idsToInclude.has(id)) {
                category.values.set(id, {
                    ...node,
                    childrenIds: node.childrenIds.filter((childId) =>
                        idsToInclude.has(childId),
                    ),
                });
            }
        }
    }

    getFolderAndParents(categoryValues, initialValue) {
        let folder = categoryValues.get(initialValue);
        const folders = [];
        while (folder) {
            folders.push(folder);
            folder = categoryValues.get(folder.parentId);
        }
        return folders;
    }
}
