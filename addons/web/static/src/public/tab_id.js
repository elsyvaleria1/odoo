// @ts-check
/** @odoo-module native */

export const TAB_HEADER = "X-Odoo-Tab";

export const TAB_ID =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
