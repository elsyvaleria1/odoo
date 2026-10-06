/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("marketing_automation/marketing_automation_context");

/** @param {Record<string, any>} context */
export function provideMarketingAutomationContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildMarketingAutomationContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useMarketingAutomationContext() {
    return envScope.use();
}
