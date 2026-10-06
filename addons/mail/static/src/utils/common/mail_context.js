/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("mail/utils/common/mail_context");

/** @param {Record<string, any>} context */
export function provideMailContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildMailContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useMailContext() {
    return envScope.use();
}

/**
 * @param {any} component
 * @returns {Record<string, any>}
 */
export function mailContextOf(component) {
    return envScope.readFrom(component);
}
