// @ts-check
/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web/core/search_model_hooks");

/** @typedef {import("@web/search/search_model").SearchModel} SearchModel */

/** @param {SearchModel} searchModel */
export function provideSearchModel(searchModel) {
    envScope.provide({ searchModel });
}

/** @param {SearchModel} searchModel */
export function provideChildSearchModel(searchModel) {
    envScope.provide({ searchModel });
}

/** @returns {SearchModel} */
export function useSearchModel() {
    return envScope.use().searchModel;
}

/**
 * @param {any} component
 * @returns {SearchModel}
 */
export function searchModelOf(component) {
    return envScope.readFrom(component).searchModel;
}
