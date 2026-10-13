/** @odoo-module native */
import { Component, proxy, useProps } from "@odoo/owl";
import { toISO } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import {
    compileViewTemplates,
    RECORD_TEMPLATE_DIRECTIVES,
    ViewCompiler,
} from "@web/views/view_compiler";

import { INFO_BOX_ATTRIBUTE } from "./geoengine_arch_parser.js";
import { displayValues } from "./record_values.js";

/**
 * @typedef {Object} FormattedField
 * @property {string|number|boolean} value
 * @property {any} raw_value
 */

/**
 * @typedef {Object} FormattedRecord
 * @property {FormattedField} id
 * @property {FormattedField} [fieldName]
 */

/**
 * @typedef {Object} RelationalModelRecord
 * @property {number} resId
 * @property {string} resModel
 * @property {string[]} fieldNames
 * @property {Object} fields
 * @property {Object} data
 * @property {Object} context
 */

const formatters = registry.category("formatters");

/**
 * @extends ViewCompiler
 * @property {string[]} OWL_DIRECTIVE_WHITELIST
 */
/** @type {string[]} */
export const WITHHELD_DIRECTIVES = ["t-set", "t-value", "t-call"];

class GeoengineViewCompiler extends ViewCompiler {}
GeoengineViewCompiler.OWL_DIRECTIVE_WHITELIST = [
    ...ViewCompiler.OWL_DIRECTIVE_WHITELIST,
    ...RECORD_TEMPLATE_DIRECTIVES.filter((d) => !WITHHELD_DIRECTIVES.includes(d)),
];

/**
 * @param {RelationalModelRecord} record
 * @param {string} fieldName
 * @returns {string|number}
 */
function getValue(record, fieldName) {
    const field = record.fields[fieldName];
    const values = displayValues(record);
    const value = values[fieldName];

    if (!field) {
        return value !== undefined ? String(value) : "";
    }

    const formatter = formatters.get(field.type, String);
    return formatter(value, { field, data: values });
}

/**
 * @param {RelationalModelRecord} record
 * @param {string} fieldName
 * @returns {any}
 */
function getRawValue(record, fieldName) {
    const field = record.fields[fieldName];
    const value = displayValues(record)[fieldName];

    if (!field) {
        return value;
    }

    switch (field.type) {
        case "many2one":
            return value?.id ?? (Array.isArray(value) ? value[0] : false);
        case "date":
        case "datetime":
            return value && toISO(value);
        default:
            return value;
    }
}

/**
 * @param {RelationalModelRecord} record
 * @returns {FormattedRecord}
 */
function getFormattedRecord(record) {
    const formatted = {
        id: {
            value: record.resId,
            raw_value: record.resId,
        },
    };

    const fieldNames = record.fieldNames || Object.keys(displayValues(record));

    for (const fieldName of fieldNames) {
        formatted[fieldName] = {
            value: getValue(record, fieldName),
            raw_value: getRawValue(record, fieldName),
        };
    }

    return formatted;
}

/**
 * @extends Component
 * @property {string} template
 * @property {Object} components
 * @property {string} INFO_BOX_ATTRIBUTE
 */
export class GeoengineRecord extends Component {
    static template = "geoengine.GeoengineRecord";
    static components = {};
    static props = null;
    static INFO_BOX_ATTRIBUTE = INFO_BOX_ATTRIBUTE;
    props = useProps(this.constructor.props);

    setup() {
        const { templates, record } = this.props;

        this.templates = compileViewTemplates(GeoengineViewCompiler, templates);

        this.dataState = proxy({
            record: record ? getFormattedRecord(record) : {},
        });

        useRecordObserver((record) =>
            Object.assign(this.dataState.record, getFormattedRecord(record)),
        );
    }

    /**
     * @returns {FormattedRecord}
     */
    get record() {
        return this.dataState.record;
    }

    /**
     * @returns {Object}
     * @returns {Object}
     * @returns {JSON}
     * @returns {FormattedRecord}
     * @returns {boolean}
     * @returns {boolean}
     * @returns {Object}
     */
    get renderingContext() {
        return {
            context: this.props.record?.context || {},
            JSON,
            record: this.dataState.record,
            __comp__: Object.assign(Object.create(this), { this: this }),
        };
    }
}
