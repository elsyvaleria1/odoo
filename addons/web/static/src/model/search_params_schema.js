// @ts-check
/** @odoo-module native */

import { assertType, t } from "@odoo/owl";

/** @type {Record<string, any>} */
export const SEARCH_PARAMS_SCHEMA = {
    context: t.object().optional(),
    domain: t.array().optional(),
    groupBy: t.array(t.string()).optional(),
    orderBy: t
        .array(t.object({ name: t.string(), asc: t.boolean().optional() }))
        .optional(),
};

const SEARCH_PARAMS_TYPE = t.strictObject(SEARCH_PARAMS_SCHEMA);

/**
 * @param {any} payload
 * @returns {string[]}
 */
export function getSearchParamsIssues(payload) {
    if (!payload || typeof payload !== "object") {
        return ["search params must be a plain object"];
    }
    const issues = [];
    /** @type {Record<string, any>} */
    const knownParams = {};
    for (const key of Object.keys(payload)) {
        if (Object.hasOwn(SEARCH_PARAMS_SCHEMA, key)) {
            knownParams[key] = payload[key];
        } else {
            issues.push(
                `unknown field '${key}' — add it to SEARCH_PARAMS_SCHEMA ` +
                    `at model/search_params_schema.js or remove the writer`,
            );
        }
    }
    try {
        assertType(knownParams, SEARCH_PARAMS_TYPE);
    } catch (error) {
        issues.push(String(error.message ?? error));
    }
    return issues;
}
