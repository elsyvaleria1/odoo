// @ts-check
/** @odoo-module native */

import { makeContext } from "@web/core/context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { domainFromTree } from "@web/core/tree/domain_from_tree";

const log = makeLogger("web.search");

/**
 * @param {any[]} conjuncts
 * @param {string} fieldName
 * @returns {{ value: any }[]}
 */
function valuesPinnedBy(conjuncts, fieldName) {
    return conjuncts.flatMap((tree) => {
        if (tree.type !== "condition" || tree.negate || tree.path !== fieldName) {
            return [];
        }
        if (tree.operator === "=") {
            return [{ value: tree.value }];
        }
        if (tree.operator === "in" && Array.isArray(tree.value)) {
            return tree.value.map((/** @type {any} */ value) => ({ value }));
        }
        return [];
    });
}

/**
 * @template {new (...args: any[]) => any} T
 * @param {T} Base
 */
export const SearchSplitDomainMixin = (Base) =>
    class extends Base {
        /**
         * @param {Record<string, any>} group
         * @param {any[]} conjuncts the edited domain replacing the group
         * @returns {Record<string, any>}
         */
        _mergedContextOfGroup(group, conjuncts) {
            const contexts = [];
            for (const activeItem of group.activeItems) {
                const searchItem = this.searchItems[activeItem.searchItemId];
                let searchedValues;
                if (searchItem?.type === "field") {
                    searchedValues = valuesPinnedBy(conjuncts, searchItem.fieldName);
                    log.logic("splitPinnedValues", () => ({
                        fieldName: searchItem.fieldName,
                        before: JSON.stringify(
                            (activeItem.autocompleteValues ?? []).map(
                                (/** @type {any} */ v) => v.value,
                            ),
                        ),
                        pinned: JSON.stringify(
                            searchedValues.map(({ value }) => value),
                        ),
                    }));
                }
                const ctx = this._getSearchItemContext(activeItem, searchedValues);
                if (ctx) {
                    contexts.push(ctx);
                }
            }
            return makeContext(contexts);
        }

        /**
         * @param {string} domain
         * @returns {Promise<any[]>}
         */
        async _domainToConjuncts(domain) {
            const tree = await this.treeProcessor.treeFromDomain(
                this.resModel,
                domain,
                !this.isDebugMode,
            );
            return !tree.negate &&
                tree.type === "connector" &&
                tree.value === "&" &&
                tree.children.length
                ? tree.children
                : [tree];
        }

        /**
         * @param {any[]} conjuncts
         * @param {Record<string, any>} [context]
         * @returns {Promise<Object[]>}
         */
        async _conjunctsToPreFilters(conjuncts, context) {
            return Promise.all(
                conjuncts.map(async (/** @type {any} */ tree) => {
                    const [description, tooltip] = await Promise.all([
                        this.treeProcessor.getDomainTreeDescription(
                            this.resModel,
                            tree,
                        ),
                        this.treeProcessor.getDomainTreeTooltip(this.resModel, tree),
                    ]);
                    /** @type {Record<string, any>} */
                    const preFilter = {
                        description,
                        tooltip,
                        domain: domainFromTree(tree),
                        invisible: "True",
                        ephemeral: true,
                        type: "filter",
                    };
                    if (context) {
                        preFilter.context = context;
                    }
                    return preFilter;
                }),
            );
        }

        /**
         * @param {Record<string, any>} group
         * @returns {Record<string, any>|undefined}
         */
        _firstSearchItemOf(group) {
            return this.searchItems[group.activeItems[0]?.searchItemId];
        }

        /**
         * @param {Record<string, any>} group
         * @returns {Promise<void>}
         */
        async _loadPropertyFieldsForFavorite(group) {
            if (this._firstSearchItemOf(group)?.type !== "favorite") {
                return;
            }
            const groupBys = this._getSearchItemGroupBys(group.activeItems[0]) || [];
            const needsPropertyFields = groupBys.some((/** @type {any} */ groupBy) =>
                groupBy.split(":")[0].includes("."),
            );
            if (needsPropertyFields) {
                await this.updateSearchViewItemsProperty();
            }
        }

        /**
         * @param {Record<string, any>} group
         * @returns {number[]}
         */
        _carryOverFavoriteGroupBys(group) {
            if (this._firstSearchItemOf(group)?.type !== "favorite") {
                return [];
            }
            const activeItemGroupBys = this._getSearchItemGroupBys(
                group.activeItems[0],
            );
            if (!activeItemGroupBys.length) {
                return [];
            }
            if (this.defaultGroupBy && this.searchScope.config.viewType === "kanban") {
                const currentGroupBy = this._getGroupBy({ fallbackOnDefault: false });
                if (
                    JSON.stringify(currentGroupBy) ===
                    JSON.stringify(this.defaultGroupBy)
                ) {
                    return [];
                }
            }
            /** @type {number[]} */
            const newGroupByIds = [];
            for (const activeItemGroupBy of activeItemGroupBys) {
                const [fieldName, interval] = activeItemGroupBy.split(":");
                const newGroupById = this.createNewGroupBy(fieldName, {
                    interval,
                    invisible: true,
                });
                if (newGroupById !== undefined) {
                    newGroupByIds.push(newGroupById);
                }
            }
            const isNewGroupBy = (/** @type {any} */ queryElem) =>
                newGroupByIds.includes(queryElem.searchItemId);
            this.query = /** @type {any[]} */ ([
                ...this.query.filter(isNewGroupBy),
                ...this.query.filter(
                    (/** @type {any} */ queryElem) => !isNewGroupBy(queryElem),
                ),
            ]);
            return newGroupByIds;
        }

        /**
         * @param {number[]} newFilterIds
         * @param {Record<string, any>|null} anchor
         */
        _moveQueryElemsAfter(newFilterIds, anchor) {
            const isNewFilter = (/** @type {any} */ queryElem) =>
                newFilterIds.includes(queryElem.searchItemId);
            /** @type {any[]} */
            const newQueryElems = this.query.filter(isNewFilter);
            /** @type {any[]} */
            const otherQueryElems = this.query.filter(
                (/** @type {any} */ queryElem) => !isNewFilter(queryElem),
            );
            const anchorIndex = anchor ? otherQueryElems.indexOf(anchor) : -1;
            const at = anchorIndex + 1;
            this.query = [
                ...otherQueryElems.slice(0, at),
                ...newQueryElems,
                ...otherQueryElems.slice(at),
            ];
        }

        /**
         * @param {string} domain
         * @param {number} [groupId]
         */
        async splitAndAddDomain(domain, groupId) {
            const findGroup = () =>
                groupId
                    ? this._getGroups().find((/** @type {any} */ g) => g.id === groupId)
                    : null;
            let group = findGroup();
            const conjuncts = await this._domainToConjuncts(domain);
            const context = group
                ? this._mergedContextOfGroup(group, conjuncts)
                : undefined;
            const preFilters = await this._conjunctsToPreFilters(conjuncts, context);
            if (group) {
                await this._loadPropertyFieldsForFavorite(group);
            }
            const edited = group;
            group = findGroup();
            log.logic("splitAndAddDomain", () => ({
                groupId,
                groupFound: Boolean(edited),
                groupStillActive: Boolean(group),
                preFilters: preFilters.length,
            }));

            this._withNotificationsBlocked(() => {
                let anchor = null;
                if (group) {
                    const replacedIndex = this.query.findIndex(
                        (/** @type {any} */ queryElem) =>
                            queryElem.searchItemId ===
                            group.activeItems[0].searchItemId,
                    );
                    if (replacedIndex > 0) {
                        anchor = this.query[replacedIndex - 1];
                    }
                    this._carryOverFavoriteGroupBys(group);
                    this.deactivateGroup(groupId);
                }

                const newFilterIds = preFilters.flatMap((preFilter) =>
                    this.createNewFilters([preFilter]),
                );

                if (group) {
                    this._moveQueryElemsAfter(newFilterIds, anchor);
                }
            });

            await this._notify();
        }
        /**
         * @param {object} [target]
         * @param {string} [target.domain]
         * @param {number} [target.groupId]
         */
        async spawnCustomFilterDialog({ domain, groupId } = {}) {
            const editing = domain !== undefined;
            this.dialog.add(this.DomainSelectorDialog, {
                resModel: this.resModel,
                ...(editing ? {} : { defaultConnector: "|" }),
                domain: editing ? domain : this.getDefaultDomain(this.searchViewFields),
                context: this.domainEvalContext,
                onConfirm: (/** @type {string} */ nextDomain) => {
                    if (!editing || nextDomain !== domain) {
                        this.splitAndAddDomain(nextDomain, groupId);
                    }
                },
                disableConfirmButton: (/** @type {string} */ domain) => domain === `[]`,
                title: _t("Custom Filter"),
                confirmButtonText: _t("Search"),
                discardButtonText: _t("Discard"),
                isDebugMode: this.isDebugMode,
            });
        }
    };
