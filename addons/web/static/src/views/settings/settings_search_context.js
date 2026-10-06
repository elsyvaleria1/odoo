// @ts-check
/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web/views/settings/settings_search_context");

/** @param {Record<string, any>} context */
export function provideSettingsSearchContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildSettingsSearchContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useSettingsSearchContext() {
    return envScope.use();
}
