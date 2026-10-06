/** @odoo-module native */
import { _t } from "@web/core/translation";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { ViewArchParser } from "@web/views/view_arch_parser";
import { getActiveActions } from "@web/views/view_utils";

const GRID_BOOLEAN_ATTRIBUTES = {
    hide_line_total: "hideLineTotal",
    hide_column_total: "hideColumnTotal",
    barchart_total: "hasBarChartTotal",
    create_inline: "createInline",
    display_empty: "displayEmpty",
    editable: "editable",
};

/**
 * @typedef {import("@web/views/ir/view_ir_schema").ViewIRNode} ViewIRNode
 * @typedef {import("@web/views/ir/view_ir_schema").GridGridAttrs} GridAttrs
 * @typedef {import("@web/views/ir/view_ir_schema").GridFieldAttrs} GridFieldAttrs
 * @typedef {import("@web/views/ir/view_ir_schema").GridRangeAttrs} GridRangeAttrs
 */

export class GridArchParser extends ViewArchParser {
    /** @type {"element" | "ir"} */
    static consumes = "ir";

    /**
     * @param {ViewIRNode | Element | string} arch
     * @param {Record<string, any>} models
     * @param {string} modelName
     */
    parse(arch, models, modelName) {
        const ir = this.toIR(arch);
        const archInfo = {
            activeActions: getActiveActions(ir),
            hideLineTotal: false,
            hideColumnTotal: false,
            hasBarChartTotal: false,
            createInline: false,
            displayEmpty: false,
            buttons: [],
            activeRangeName: "",
            ranges: {},
            sectionField: null,
            rowFields: [],
            columnFieldName: "",
            measureField: {
                name: "__count",
                aggregator: "sum",
                readonly: true,
                string: _t("Count"),
            },
            readonlyField: null,
            widgetPerFieldName: {},
            editable: false,
            formViewId: false,
        };
        const fields = models[modelName].fields;
        this.visitIR(ir, archInfo, {
            grid: this._parseGridNode,
            field: (node, info) => this._parseFieldNode(node, info, fields),
            button: this._parseButtonNode,
        });
        // `measureField` always exists -- it defaults to a readonly `__count`,
        // which is what makes a grid declaring no measure uneditable.
        archInfo.editable =
            archInfo.editable &&
            !archInfo.measureField.readonly &&
            archInfo.measureField.aggregator === "sum";
        return archInfo;
    }

    /**
     * @param {ViewIRNode} node
     * @param {Record<string, any>} archInfo
     */
    _parseGridNode(node, archInfo) {
        /** @type {GridAttrs} */
        const attrs = node.attrs || {};
        for (const [attribute, key] of Object.entries(GRID_BOOLEAN_ATTRIBUTES)) {
            if (attribute in attrs) {
                archInfo[key] = exprToBoolean(attrs[attribute]);
            }
        }
        if (attrs.action !== undefined && attrs.type !== undefined) {
            archInfo.openAction = {
                name: attrs.action,
                type: attrs.type,
            };
        }
        if (attrs.form_view_id !== undefined) {
            archInfo.formViewId = parseInt(attrs.form_view_id, 10);
        }
    }

    /**
     * @param {ViewIRNode} node
     * @param {Record<string, any>} archInfo
     * @param {Record<string, any>} fields
     */
    _parseFieldNode(node, archInfo, fields) {
        /** @type {GridFieldAttrs} */
        const attrs = node.attrs || {};
        const fieldName = /** @type {string} */ (attrs.name); // exists (rng validation)
        const fieldInfo = fields[fieldName];
        const type = attrs.type || "row";
        if (attrs.widget !== undefined && ["row", "measure"].includes(type)) {
            archInfo.widgetPerFieldName[fieldName] = attrs.widget;
        }
        switch (type) {
            case "row": {
                // Only a row groups by a bare field; a col groups by its
                // <range> step and a measure does not group at all.
                const rowField = {
                    name: fieldName,
                    invisible: exprToBoolean(attrs.invisible || ""),
                    granularity: this._extractGranularity(node, fieldInfo),
                };
                if (exprToBoolean(attrs.section || "") && !archInfo.sectionField) {
                    archInfo.sectionField = rowField;
                } else {
                    archInfo.rowFields.push(rowField);
                }
                break;
            }
            case "col": {
                archInfo.columnFieldName = fieldName;
                Object.assign(archInfo, this._extractRanges(node));
                break;
            }
            case "measure":
                archInfo.measureField = {
                    name: fieldName,
                    aggregator: this._extractAggregator(node, fieldInfo),
                    string: attrs.string || fieldInfo.string,
                    readonly: fieldInfo.readonly,
                };
                break;
            case "readonly":
                archInfo.readonlyField = {
                    name: fieldName,
                    aggregator: this._extractAggregator(node, fieldInfo),
                };
                break;
        }
    }

    /**
     * @param {ViewIRNode} node
     * @param {Record<string, any>} archInfo
     */
    _parseButtonNode(node, archInfo) {
        archInfo.buttons.push({
            ...this.processButton(node),
            type: "button",
            id: archInfo.buttons.length,
        });
    }

    /**
     * The aggregate function a measure or readonly field is read_group'd with.
     * Both are asked for as `field:aggregator`, and a field type that declares
     * no default -- a boolean, say -- leaves nothing to put after the colon.
     * Neither of the two ways that used to end is legible from where it
     * surfaced: `field:undefined` comes back from the server as
     * `Invalid aggregation function "undefined"`, and a bare `field` is
     * accepted and then read off the group as a value that is not there,
     * crashing the client on `object null is not iterable`.
     *
     * @private
     * @param {ViewIRNode} node the <field> node.
     * @param {Object} fieldInfo the field's description.
     * @returns {string}
     */
    _extractAggregator(node, fieldInfo) {
        /** @type {GridFieldAttrs} */
        const attrs = node.attrs || {};
        const aggregator = attrs.operator || fieldInfo.aggregator;
        if (!aggregator) {
            throw new Error(
                `Grid view: the field "${attrs.name}" is ` +
                    `aggregated, and its type (${fieldInfo.type}) declares no ` +
                    `default aggregator, so it must state one -- ` +
                    `e.g. operator="bool_or".`,
            );
        }
        return aggregator;
    }

    /**
     * The granularity a row or section field groups by. read_group refuses a
     * date or datetime groupby that does not state one, and the arch is the
     * only place a row field can say it -- unlike a search groupby, which
     * carries its own. Saying nothing on a date field is therefore not a
     * default, it is an error the server would report far from its cause.
     *
     * @private
     * @param {ViewIRNode} node the <field> node.
     * @param {Object} fieldInfo the field's description.
     * @returns {string|undefined}
     */
    _extractGranularity(node, fieldInfo) {
        /** @type {GridFieldAttrs} */
        const attrs = node.attrs || {};
        const granularity = attrs.granularity;
        if (granularity) {
            return granularity;
        }
        if (["date", "datetime"].includes(fieldInfo.type)) {
            throw new Error(
                `Grid view: the row field "${attrs.name}" is a ` +
                    `${fieldInfo.type} and must declare a granularity, ` +
                    `e.g. granularity="month".`,
            );
        }
        return undefined;
    }

    /**
     * The <range>s a col field declares, and the one the view opens on: the
     * first declared `default="1"`, else the first declared at all. Several
     * defaults used to elect the last, the one way round nobody reading the
     * arch top to bottom would expect.
     *
     * @private
     * @param {ViewIRNode} colNode the col <field> node.
     * @returns {{ranges: Object<string, Object>, activeRangeName: string}}
     */
    _extractRanges(colNode) {
        const ranges = {};
        let activeRangeName = "";
        for (const rangeNode of colNode.children || []) {
            /** @type {GridRangeAttrs} */
            const rangeAttrs = rangeNode.attrs || {};
            const rangeName = rangeAttrs.name;
            ranges[rangeName] = {
                name: rangeName,
                description: rangeAttrs.string ?? null,
                span: rangeAttrs.span ?? null,
                step: rangeAttrs.step ?? null,
                hotkey: rangeAttrs.hotkey ?? null,
                default: exprToBoolean(rangeAttrs.default),
            };
            if (ranges[rangeName].default && !activeRangeName) {
                activeRangeName = rangeName;
            }
        }
        return {
            ranges,
            activeRangeName: activeRangeName || Object.keys(ranges)[0] || "",
        };
    }
}
