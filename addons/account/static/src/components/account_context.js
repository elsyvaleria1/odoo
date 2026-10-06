/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("account/components/account_context");

/** @param {Record<string, any>} context */
export function provideAccountContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildAccountContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useAccountContext() {
    return envScope.use();
}
