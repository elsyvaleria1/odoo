/** @odoo-module native */

export const ACTIVE_IDS_PLACEHOLDER = "{ACTIVE_IDS}";

/**
 * @param {string} domainText
 * @returns {string}
 */
export function nameActiveIds(domainText) {
    return domainText
        .replace(/(["'])\{ACTIVE_IDS\}\1/g, "ACTIVE_IDS")
        .replace(/\{ACTIVE_IDS\}/g, "ACTIVE_IDS");
}

/**
 * @param {*} node
 * @param {number[]} ids
 * @returns {*}
 */
export function withActiveIds(node, ids) {
    if (node === ACTIVE_IDS_PLACEHOLDER) {
        return ids;
    }
    if (Array.isArray(node)) {
        return node.map((item) => withActiveIds(item, ids));
    }
    if (node && typeof node === "object") {
        return Object.fromEntries(
            Object.entries(node).map(([key, value]) => [
                key,
                withActiveIds(value, ids),
            ]),
        );
    }
    return node;
}
