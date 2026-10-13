// @ts-check
/** @odoo-module native */

import { markup } from "@odoo/owl";

/**
 * @template {{ help?: any }} T
 * @param {T} action
 * @returns {T}
 */
export function withMarkupHelp(action) {
    if (action.help) {
        action.help = markup(action.help);
    }
    return action;
}
