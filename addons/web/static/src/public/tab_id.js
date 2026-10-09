// @ts-check
/** @odoo-module native */

// names this page load to the server (X-Odoo-Tab) on the requests that change
// shared state, so that a notice the change causes (@bus/public/live_fragments) is
// told apart from one another tab caused
export const TAB_HEADER = "X-Odoo-Tab";

export const TAB_ID =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
