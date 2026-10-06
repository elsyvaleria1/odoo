/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("hr_holidays/views/time_off_context");

/** @param {Record<string, any>} context */
export function provideTimeOffContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildTimeOffContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useTimeOffContext() {
    return envScope.use();
}
