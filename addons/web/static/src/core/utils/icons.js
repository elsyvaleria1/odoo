// @ts-check
/** @odoo-module native */

export const FA_STYLE_CLASSES = ["fa-solid", "fa-regular", "fa-brands"];

const ICON_TAGS = ["I", "SPAN"];

export const iconClasses = ["fa", "fab", "fad", "far", "oi", ...FA_STYLE_CLASSES];

export const ICON_CLASS_SELECTOR = iconClasses.map((cls) => `.${cls}`).join(", ");

export const ICON_SELECTOR = ICON_TAGS.map((tag) =>
    iconClasses.map((cls) => `${tag}.${cls}`).join(", "),
).join(", ");

export const FONT_AWESOME_SELECTOR = ICON_TAGS.map((tag) =>
    iconClasses
        .filter((cls) => cls !== "oi")
        .map((cls) => `${tag}.${cls}`)
        .join(", "),
).join(", ");

/**
 * @param {?Node} [node]
 * @returns {boolean}
 */
export function isIconElement(node) {
    return !!(
        node &&
        ICON_TAGS.includes(node.nodeName) &&
        iconClasses.some((cls) => /** @type {Element} */ (node).classList.contains(cls))
    );
}

/**
 * @param {string} iconClass
 * @returns {string}
 */
export function faIconClass(iconClass) {
    if (FA_STYLE_CLASSES.some((prefix) => iconClass.startsWith(prefix))) {
        return iconClass;
    }
    const glyph = iconClass.startsWith("fa fa-") ? iconClass.slice(3) : iconClass;
    return `fa-solid ${glyph}`;
}
