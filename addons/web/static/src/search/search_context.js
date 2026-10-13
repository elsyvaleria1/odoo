// @ts-check
/** @odoo-module native */

import { makeContext } from "@web/core/context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { evaluateExpr } from "@web/core/py_js/py";
import { _t } from "@web/core/translation";
import { deepCopy } from "@web/core/utils/collections/objects";

/** @import { ActiveItem, AutocompleteValue, FieldItem, QueryGroup, SearchItems } from "./search_types" */

const log = makeLogger("web.search");

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function isContextDict(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * @param {FieldItem} searchItem
 * @param {{ value: any }[]} searchedValues
 * @returns {Record<string, any>|null}
 */
export function computeDefaultSeed(searchItem, searchedValues) {
    const defaultValue = searchItem.defaultAutocompleteValue;
    if (!searchItem.isDefault || searchItem.fieldType !== "many2one" || !defaultValue) {
        return null;
    }
    const held = searchedValues.some(({ value }) => value === defaultValue.value);
    log.logic("defaultSeed", () => ({
        fieldName: searchItem.fieldName,
        defaultValue: defaultValue.value,
        searchedValues: JSON.stringify(searchedValues.map(({ value }) => value)),
        held,
    }));
    return held ? { [`default_${searchItem.fieldName}`]: defaultValue.value } : null;
}

/**
 * @param {ActiveItem} activeItem
 * @param {SearchItems} searchItems
 * @param {{ value: any }[]} [searchedValues]
 * @returns {Record<string, any>|null}
 */
export function computeSearchItemContext(
    activeItem,
    searchItems,
    searchedValues = activeItem.autocompleteValues ?? [],
) {
    const { searchItemId } = activeItem;
    const searchItem = searchItems[searchItemId];
    switch (searchItem.type) {
        case "field": {
            /** @type {Record<string, any>} */
            let context = {};
            if (searchItem.context) {
                const self = (activeItem.autocompleteValues ?? []).map(
                    (/** @type {AutocompleteValue} */ autocompleteValue) =>
                        autocompleteValue.value,
                );
                context = evaluateExpr(searchItem.context, { self });
                if (!isContextDict(context)) {
                    throw new Error(
                        _t("Failed to evaluate the context: %(context)s.", {
                            context: searchItem.context,
                        }),
                    );
                }
            }
            return Object.assign(
                context,
                computeDefaultSeed(searchItem, searchedValues),
            );
        }
        case "favorite":
        case "filter":
            return makeContext([searchItem.context && deepCopy(searchItem.context)]);
        default:
            return null;
    }
}

/**
 * @param {QueryGroup[]} groups
 * @param {Record<string, any>} userContext
 * @param {(activeItem: ActiveItem) => Record<string, any>|null} getSearchItemContext
 * @returns {Record<string, any>}
 */
export function computeSearchContext(groups, userContext, getSearchItemContext) {
    const contexts = [userContext];
    for (const group of groups) {
        for (const activeItem of group.activeItems) {
            const context = getSearchItemContext(activeItem);
            if (context) {
                contexts.push(context);
            }
        }
    }
    return makeContext(contexts);
}
