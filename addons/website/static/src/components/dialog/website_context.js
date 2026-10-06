/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("website/components/dialog/website_context");

/** @param {Record<string, any>} context */
export function provideWebsiteContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildWebsiteContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useWebsiteContext() {
    return envScope.use();
}
