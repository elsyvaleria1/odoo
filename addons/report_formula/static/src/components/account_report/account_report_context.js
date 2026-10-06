/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope(
    "report_formula/components/account_report/account_report_context",
);

/** @param {Record<string, any>} context */
export function provideAccountReportContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildAccountReportContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useAccountReportContext() {
    return envScope.use();
}
