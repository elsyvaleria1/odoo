/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("portal/chatter/core/portal_context");

/** @param {Record<string, any>} context */
export function providePortalContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildPortalContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function usePortalContext() {
    return envScope.use();
}

/**
 * @param {any} component
 * @returns {Record<string, any>}
 */
export function portalContextOf(component) {
    return envScope.readFrom(component);
}
