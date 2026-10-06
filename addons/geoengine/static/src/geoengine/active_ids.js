/** @odoo-module native */

export const ACTIVE_IDS_PLACEHOLDER = "{ACTIVE_IDS}";

/**
 * A layer domain names the drawn records with the {ACTIVE_IDS} placeholder,
 * quoted or not; this turns it into the ACTIVE_IDS variable an evaluation
 * context can bind.
 *
 * @param {string} domainText
 * @returns {string}
 */
export function nameActiveIds(domainText) {
    return domainText
        .replace(/(["'])\{ACTIVE_IDS\}\1/g, "ACTIVE_IDS")
        .replace(/\{ACTIVE_IDS\}/g, "ACTIVE_IDS");
}

/**
 * The drawn records' ids in place of every {ACTIVE_IDS} placeholder of a
 * domain the server evaluated.
 *
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
