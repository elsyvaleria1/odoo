// @ts-check
/** @odoo-module native */
import { _t } from "@web/core/translation";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { ViewArchParser } from "@web/views/view_arch_parser";

import { INTERVALS, MODES, TIMELINES } from "./cohort_model.js";

/**
 * @typedef {import("@web/views/ir/view_ir_schema").ViewIRNode} ViewIRNode
 * @typedef {import("@web/views/ir/view_ir_schema").CohortCohortAttrs} CohortAttrs
 * @typedef {import("@web/views/ir/view_ir_schema").CohortFieldAttrs} CohortFieldAttrs
 */

export class CohortArchParser extends ViewArchParser {
    /** @type {"element" | "ir"} */
    static consumes = "ir";

    /**
     * @param {ViewIRNode | Element | string} arch
     * @param {Record<string, any>} [models]
     * @param {string} [modelName]
     * @returns {Record<string, any>}
     */
    parse(arch, models, modelName) {
        const fields = (modelName && models?.[modelName]?.fields) || {};
        /** @type {Record<string, any>} */
        const archInfo = {
            fieldAttrs: {},
            widgets: {},
        };
        return this.visitIR(this.toIR(arch), archInfo, {
            cohort: this.parseRootNode.bind(this, fields),
            field: this.parseFieldNode,
        });
    }

    /**
     * @param {Record<string, any>} fields
     * @param {ViewIRNode} node
     * @param {Record<string, any>} archInfo
     */
    parseRootNode(fields, node, archInfo) {
        /** @type {CohortAttrs} */
        const attrs = node.attrs || {};
        if (attrs.disable_linking !== undefined) {
            archInfo.disableLinking = exprToBoolean(attrs.disable_linking);
        }
        if (attrs.string) {
            archInfo.title = attrs.string;
        }
        const dateStart = attrs.date_start;
        if (dateStart) {
            archInfo.dateStart = dateStart;
            archInfo.dateStartString = fields[dateStart].string;
        } else {
            throw new Error(_t('Cohort view has not defined "date_start" attribute.'));
        }
        const dateStop = attrs.date_stop;
        if (dateStop) {
            archInfo.dateStop = dateStop;
            archInfo.dateStopString = fields[dateStop].string;
        } else {
            throw new Error(_t('Cohort view has not defined "date_stop" attribute.'));
        }
        const mode = attrs.mode || "retention";
        if (mode && MODES.includes(mode)) {
            archInfo.mode = mode;
        } else {
            throw new Error(
                _t(
                    "The argument %(mode)s is not a valid mode. Here are the modes: %(modes)s",
                    { mode, modes: MODES },
                ),
            );
        }
        const timeline = attrs.timeline || "forward";
        if (timeline && TIMELINES.includes(timeline)) {
            archInfo.timeline = timeline;
        } else {
            throw new Error(
                _t(
                    "The argument %(timeline)s is not a valid timeline. Here are the timelines: %(timelines)s",
                    { timeline, timelines: TIMELINES },
                ),
            );
        }
        archInfo.measure = attrs.measure || "__count";
        const interval = attrs.interval || "day";
        if (interval && interval in INTERVALS) {
            archInfo.interval = interval;
        } else {
            throw new Error(
                _t(
                    "The argument %(interval)s is not a valid interval. Here are the intervals: %(intervals)s",
                    { interval, intervals: INTERVALS },
                ),
            );
        }
    }

    /**
     * @param {ViewIRNode} node
     * @param {Record<string, any>} archInfo
     */
    parseFieldNode(node, archInfo) {
        /** @type {CohortFieldAttrs} */
        const attrs = node.attrs || {};
        const fieldName = /** @type {string} */ (attrs.name);

        archInfo.fieldAttrs[fieldName] = {};
        if (attrs.string !== undefined) {
            archInfo.fieldAttrs[fieldName].string = attrs.string;
        }
        if (attrs.invisible === "True" || attrs.invisible === "1") {
            archInfo.fieldAttrs[fieldName].isInvisible = true;
            return;
        }
        if (attrs.widget !== undefined) {
            archInfo.widgets[fieldName] = attrs.widget;
        }
    }
}
