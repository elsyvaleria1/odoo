/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("knowledge/js/knowledge_context");

/** @param {Record<string, any>} context */
export function provideKnowledgeContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildKnowledgeContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useKnowledgeContext() {
    return envScope.use();
}

/**
 * @param {any} component
 * @returns {Record<string, any>}
 */
export function knowledgeContextOf(component) {
    return envScope.readFrom(component);
}
