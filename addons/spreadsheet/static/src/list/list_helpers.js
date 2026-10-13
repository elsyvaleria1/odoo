/** @odoo-module native */
// @ts-check

import { helpers } from "@odoo/o-spreadsheet";

const { getFunctionsFromTokens } = helpers;

/** @typedef {import("@odoo/o-spreadsheet").Token} Token */

/**
 * @param {Token[]} tokens
 * @returns {number}
 */
export function getNumberOfListFormulas(tokens) {
    return getFunctionsFromTokens(tokens, ["ODOO.LIST", "ODOO.LIST.HEADER"]).length;
}

/**
 * @param {Token[]} tokens
 * @returns {import("../helpers/odoo_functions_helpers").OdooFunctionDescription|undefined}
 */
export function getFirstListFunction(tokens) {
    return getFunctionsFromTokens(tokens, ["ODOO.LIST", "ODOO.LIST.HEADER"])[0];
}
