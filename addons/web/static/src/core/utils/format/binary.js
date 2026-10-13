// @ts-check
/** @odoo-module native */

import { localization } from "@web/core/l10n/localization";
import { _t } from "@web/core/translation";

/**
 * @param {string} value
 * @returns {boolean}
 */
export function isBinarySize(value) {
    return /^\d+(\.\d*)? [^0-9]+$/.test(value);
}

/**
 * @param {number} maxBytes
 * @returns {number}
 */
export function toBase64Length(maxBytes) {
    return Math.ceil((maxBytes * 4) / 3);
}

/**
 * @param {string} text
 * @returns {string}
 */
export function textToBase64(text) {
    return new TextEncoder().encode(text).toBase64();
}

const SIZE_UNITS = "Bytes|KB|MB|GB|TB|PB|EB|ZB|YB";

/**
 * @param {number} size
 * @param {{ localized?: boolean }} [options]
 * @returns {string}
 */
export function humanSize(size, { localized = true } = {}) {
    const units = (localized ? _t("Bytes|KB|MB|GB|TB|PB|EB|ZB|YB") : SIZE_UNITS).split(
        "|",
    );
    let i = 0;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        ++i;
    }
    const fixed = size.toFixed(2);
    const formatted = localized ? fixed.replace(".", localization.decimalPoint) : fixed;
    return `${formatted} ${units[i].trim()}`;
}
