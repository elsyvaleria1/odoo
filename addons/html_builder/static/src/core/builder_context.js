/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("html_builder/core/builder_context");

/** @param {Record<string, any>} context */
export function provideBuilderContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildBuilderContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useBuilderContext() {
    return envScope.use();
}
