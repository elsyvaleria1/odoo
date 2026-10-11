/** @odoo-module native */
import {
    STUDIO_ICON_BACKGROUND_COLORS as BG_COLORS,
    STUDIO_ICON_COLORS as COLORS,
} from "@web/core/colors/colors";

export { BG_COLORS, COLORS };

export function getFontAwesomeIcons() {
    const icons = [];
    for (const styleSheet of document.styleSheets) {
        if (!styleSheet.href || !styleSheet.href.includes("/web/")) {
            continue;
        }
        let cssRules;
        try {
            cssRules = styleSheet.cssRules;
        } catch {
            continue;
        }
        for (const rule of cssRules) {
            if (!rule.style || rule.style.length !== 1 || rule.style[0] !== "--fa") {
                continue;
            }
            const classNames = rule.selectorText
                .split(",")
                .map((selector) => selector.trim())
                .filter((selector) => /^\.fa-[a-z0-9-]+$/.test(selector));
            if (!classNames.length) {
                continue;
            }
            const searchTerms = classNames.map((selector) =>
                selector
                    .replace(".fa-", "")
                    .replace(/-o$/g, " (Outline)")
                    .replaceAll("-", " "),
            );
            icons.push({
                className: "fa-solid " + classNames[0].slice(1),
                searchTerms,
                tooltip:
                    searchTerms[0].charAt(0).toUpperCase() + searchTerms[0].slice(1),
            });
        }
    }
    return icons;
}

/**
 * @param {Integer} string_length
 * @returns {String} A random string with numbers and lower/upper case chars
 */
export function randomString(string_length) {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    let randomstring = "";
    for (let i = 0; i < string_length; i++) {
        const rnum = Math.floor(Math.random() * chars.length);
        randomstring += chars.substring(rnum, rnum + 1);
    }
    return randomstring;
}

export default {
    BG_COLORS,
    COLORS,
    randomString,
};
