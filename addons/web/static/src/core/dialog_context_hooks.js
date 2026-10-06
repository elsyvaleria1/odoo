// @ts-check
/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web/core/dialog_context_hooks");

/** @param {Record<string, any>} context */
export function provideChildDialogContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useDialogContext() {
    return envScope.use();
}

/**
 * @param {any} component
 * @returns {Record<string, any>}
 */
export function dialogContextOf(component) {
    return envScope.readFrom(component);
}
