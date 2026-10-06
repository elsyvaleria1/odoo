/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("approval/views/approval_context");

/** @param {Record<string, any>} context */
export function provideApprovalContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildApprovalContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useApprovalContext() {
    return envScope.use();
}
