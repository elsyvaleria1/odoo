/** @odoo-module native */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

/**
 * @param {Function} callback
 * @param {Number} duration
 */
export function useInterval(callback, duration) {
    let interval;
    onMounted(() => (interval = browser.setInterval(callback, duration)));
    onWillUnmount(() => browser.clearInterval(interval));
}
