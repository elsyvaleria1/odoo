/** @odoo-module native */

import { virtualOperatorFunctions } from "@web/core/tree";
import { patch } from "@web/core/utils/patch";

import {
    eliminateGeoOperators,
    introduceGeoOperators,
} from "./geo_virtual_operators.js";

patch(virtualOperatorFunctions, {
    /**
     * @param {Object} tree
     * @param {Object} [options=
     * @param {Function} [options.getFieldDef]
     * @returns {Object}
     */
    introduceVirtualOperators(tree, options = {}) {
        let result = super.introduceVirtualOperators(tree, options);

        result = introduceGeoOperators(result, options);

        return result;
    },

    /**
     * @param {Object} tree
     * @param {Object} [options=
     * @returns {Object}
     */
    eliminateVirtualOperators(tree, options = {}) {
        let result = eliminateGeoOperators(tree, options);

        result = super.eliminateVirtualOperators(result, options);

        return result;
    },
});
