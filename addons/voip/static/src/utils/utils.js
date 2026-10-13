/** @odoo-module native */
import { normalize } from "@web/core/l10n/utils";

/**
 * @param {string} phoneNumber
 * @returns {string}
 */
export function cleanPhoneNumber(phoneNumber) {
    return phoneNumber.replace(/[-()\s/.\u00AD]/g, "");
}

const editableInputTypes = new Set([
    "date",
    "datetime-local",
    "email",
    "month",
    "number",
    "password",
    "search",
    "tel",
    "text",
    "time",
    "url",
    "week",
]);

/** @returns {boolean} */
export function isCurrentFocusEditable() {
    const el = document.activeElement;
    if (!el) {
        return false;
    }
    if (el.isContentEditable) {
        return true;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === "textarea") {
        return true;
    }
    if (tag === "input") {
        const inputType = el.getAttribute("type")?.toLowerCase() || "text";
        return editableInputTypes.has(inputType);
    }
    return false;
}

export function isSubstring(targetString, substring) {
    if (!targetString) {
        return false;
    }
    return normalize(targetString).includes(normalize(substring));
}

/**
 * @param {string} targetNumber
 * @param {string} searchTerms
 * @returns {{before: string, match: string, after: string} | null}
 */
export function matchPhoneNumber(targetNumber, searchTerms) {
    if (/[a-zA-Z]/.test(searchTerms)) {
        return null;
    }
    const r = String.raw;
    const hasPlusPrefix = searchTerms.trim().startsWith("+");
    const sanitizedSearchTerms = searchTerms.replace(/[^0-9*#;,]/g, "");
    let regexString = Array.from(sanitizedSearchTerms, RegExp.escape).join(r`\D*`);
    if (!regexString && !hasPlusPrefix) {
        return null;
    }
    if (hasPlusPrefix) {
        regexString = r`\+\D*${regexString}`;
    }
    const regex = new RegExp(`(^.*?)(${regexString})(.*?$)`, "i");
    const [, before, match, after] = targetNumber.match(regex) ?? [];
    if (match) {
        return { before, match, after };
    }
    return null;
}
