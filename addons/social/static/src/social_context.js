/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("social/social_context");

/** @param {Record<string, any>} context */
export function provideSocialContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildSocialContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useSocialContext() {
    return envScope.use();
}
