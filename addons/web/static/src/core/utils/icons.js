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
 * Font Awesome 7 draws nothing for a glyph class without a style class, so a
 * bare `fa-clipboard` — the FA4 spelling every arch attribute and most
 * callers still use — is completed to `fa-solid fa-clipboard`; the FA4 `fa `
 * base is dropped on the way. A class that already names its style is kept.
 *
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
