/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("survey/question_page/survey_context");

/** @param {Record<string, any>} context */
export function provideSurveyContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildSurveyContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useSurveyContext() {
    return envScope.use();
}
