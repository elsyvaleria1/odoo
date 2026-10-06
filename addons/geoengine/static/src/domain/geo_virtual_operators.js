/** @odoo-module native */

import { condition, operate } from "@web/core/tree";

import { ACTIVE_IDS_PLACEHOLDER } from "../geoengine/active_ids.js";

/**
 * @param {Object} tree
 * @param {Object} [options=
 * @returns {Object}
 */
export function introduceGeoOperators(tree, options = {}) {
    function _introduceGeoOperator(c) {
        const { path, operator, value, negate } = c;

        if (operator === "in" && value === ACTIVE_IDS_PLACEHOLDER) {
            return condition(path, "geo_in_active", value, negate);
        }

        if (operator === "not in" && value === ACTIVE_IDS_PLACEHOLDER) {
            return condition(path, "geo_not_in_active", value, negate);
        }

        return;
    }

    return operate(_introduceGeoOperator, tree, options);
}

/**
 * @param {Object} tree
 * @param {Object} [options=
 * @returns {Object}
 */
export function eliminateGeoOperators(tree, options = {}) {
    function _eliminateGeoOperator(c) {
        const { path, operator, value, negate } = c;

        if (operator === "geo_in_active") {
            return condition(path, "in", value, negate);
        }

        if (operator === "geo_not_in_active") {
            return condition(path, "not in", value, negate);
        }

        return;
    }

    return operate(_eliminateGeoOperator, tree, options);
}
