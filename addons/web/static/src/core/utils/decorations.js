// @ts-check
/** @odoo-module native */

/**
 * @param {string} decoration
 * @returns {string}
 */
export function getClassNameFromDecoration(decoration) {
    if (decoration === "bf") {
        return "fw-bold";
    } else if (decoration === "it") {
        return "fst-italic";
    }
    return `text-${decoration}`;
}

/**
 * @param {Record<string, string>} attrs
 * @returns {{ class: string, condition: string }[]}
 */
export function getDecoration(attrs) {
    const decorations = [];
    for (const [name, condition] of Object.entries(attrs)) {
        if (name.startsWith("decoration-")) {
            decorations.push({
                class: getClassNameFromDecoration(name.replace("decoration-", "")),
                condition,
            });
        }
    }
    return decorations;
}
