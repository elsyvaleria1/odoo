/** @odoo-module native */

import { press } from "@odoo/hoot-dom";

/** @param {string[]} chars */
export async function simulateBarCode(chars) {
    for (const char of chars) {
        await press(char);
    }
}
