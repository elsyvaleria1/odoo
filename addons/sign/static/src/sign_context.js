/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("sign/sign_context");

/** @param {Record<string, any>} context */
export function provideSignContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildSignContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useSignContext() {
    return envScope.use();
}
