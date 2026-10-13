/** @odoo-module native */
// @ts-check

/**
 * @typedef {object} OdooFunctionDescription
 * @property {string} functionName
 * @property {import("@odoo/o-spreadsheet").AST[]} args
 */

/**
 * @param {import("@odoo/o-spreadsheet").EnrichedToken} tokenAtCursor
 * @returns {string | undefined}
 */
export function extractDataSourceId(tokenAtCursor) {
    const idAst = tokenAtCursor.functionContext?.args[0];
    if (!idAst || !["STRING", "NUMBER"].includes(idAst.type)) {
        return;
    }
    return idAst.value;
}
