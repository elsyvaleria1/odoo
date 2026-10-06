/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web_gantt/gantt_context");

/** @param {Record<string, any>} context */
export function provideGanttContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildGanttContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useGanttContext() {
    return envScope.use();
}
