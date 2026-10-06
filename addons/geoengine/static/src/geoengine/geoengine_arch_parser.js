/** @odoo-module native */
import { deepCopy } from "@web/core/utils/collections/objects";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { stringToOrderBy } from "@web/core/utils/order_by";
import { parseFieldNode } from "@web/views/field_arch";
import { irToElement, literalNbsp } from "@web/views/ir/view_ir";
import { ViewArchParser, visitIR } from "@web/views/view_arch_parser";
import { getActiveActions } from "@web/views/view_utils";

/**
 * @typedef {import("@web/views/ir/view_ir_schema").ViewIRNode} ViewIRNode
 * @typedef {import("@web/views/ir/view_ir_schema").GeoengineGeoengineAttrs} GeoengineAttrs
 */
import { makeGeoLogger } from "../geo_debug.js";

const debugLog = makeGeoLogger("GeoengineArchParser");

export const INFO_BOX_ATTRIBUTE = "info_box";

/**
 * @typedef {Object} ParsedArchitecture
 * @property {Object} activeActions
 * @property {string|null} className
 * @property {string} defaultGroupBy
 * @property {Object.<string, XMLElement>} templateDocs
 * @property {Object.<string, Object>} fieldNodes
 * @property {number} [limit]
 * @property {number} [countLimit]
 * @property {Array<{name: string, asc: boolean}>} [defaultOrder]
 * @property {boolean} editable
 * @property {boolean} [webglTrail]
 */

export class GeoengineArchParser extends ViewArchParser {
    /** @type {"element" | "ir"} */
    static consumes = "ir";

    /** @param {GeoengineAttrs} attrs */
    _extractPaginationAttributes(attrs) {
        return {
            limit: attrs.limit ?? null,
            countLimit: attrs.count_limit ?? null,
        };
    }

    /** @param {ViewIRNode} ir */
    _extractActionAttributes(ir) {
        return { activeActions: getActiveActions(ir) };
    }

    /**
     * @param {GeoengineAttrs} attrs
     * @param {(name: string, defaultValue?: boolean) => boolean} getBoolAttr
     */
    _extractFeaturesListAttributes(attrs, getBoolAttr) {
        return {
            featuresList: getBoolAttr("features_list"),
            featuresListField: attrs.features_list_field || "display_name",
            featuresListGroupBy: attrs.features_list_group_by || null,
        };
    }

    /**
     * @param {GeoengineAttrs} attrs
     * @param {(name: string, defaultValue?: boolean) => boolean} getBoolAttr
     */
    _extractTrailAttributes(attrs, getBoolAttr) {
        return {
            webglTrail: getBoolAttr("webgl_trail"),
            trailTimestampsField: attrs.trail_timestamps_field || "trail_timestamps",
            trailColorField: attrs.trail_color_field || "trail_color",
        };
    }

    /**
     * The `field_id` annotations go on the parser's own copy of the tree;
     * the `templateDocs` the compiler reads are that copy materialised.
     *
     * @param {ViewIRNode | Element | string} arch
     * @param {Record<string, any>} models
     * @param {string} modelName
     * @returns {ParsedArchitecture}
     */
    parse(arch, models, modelName) {
        const ir = deepCopy(this.toIR(arch));
        /** @type {GeoengineAttrs} */
        const attrs = ir.attrs || {};
        debugLog("parse() starting", {
            modelName,
            archTagName: ir.kind,
            hasModels: !!models,
        });

        const getBoolAttr = (name, defaultValue = false) =>
            name in attrs ? exprToBoolean(attrs[name]) : defaultValue;

        const paginationAttrs = this._extractPaginationAttributes(attrs);
        const actionAttrs = this._extractActionAttributes(ir);
        const trailAttrs = this._extractTrailAttributes(attrs, getBoolAttr);
        const featuresListAttrs = this._extractFeaturesListAttributes(
            attrs,
            getBoolAttr,
        );

        const className = attrs.class || null;
        const defaultGroupBy = attrs.default_group_by ?? null;
        const defaultOrder =
            attrs.default_order !== undefined
                ? stringToOrderBy(attrs.default_order)
                : null;
        const editable = getBoolAttr("editable");

        const { limit, countLimit } = paginationAttrs;
        const { activeActions } = actionAttrs;
        const templateDocs = {};
        const fieldNodes = {};

        debugLog("Basic attributes extracted", {
            limit,
            countLimit,
            className,
            defaultGroupBy,
            activeActions,
        });

        visitIR(ir, (node) => {
            if (node.attrs?.["t-name"] !== undefined) {
                debugLog("Template found:", node.attrs["t-name"]);
                return;
            }

            if (node.kind === "field") {
                const fieldInfo = parseFieldNode(node, models, modelName, "geoengine");
                const name = fieldInfo?.name;
                if (name) {
                    fieldNodes[name] = fieldInfo;
                    (node.attrs ??= {}).field_id = name;
                    debugLog("Field parsed:", {
                        name,
                        type: fieldInfo.type,
                        widget: fieldInfo.widget,
                    });
                }
            }
        });
        for (const templateDoc of irToElement(ir, {
            text: literalNbsp,
        }).querySelectorAll("[t-name]")) {
            templateDocs[/** @type {string} */ (templateDoc.getAttribute("t-name"))] =
                templateDoc;
        }

        debugLog("✓ Parse completed successfully", {
            modelName,
            totalFields: Object.keys(fieldNodes).length,
            webglTrail: trailAttrs.webglTrail,
        });

        return {
            limit: limit && parseInt(limit, 10),
            countLimit: countLimit && parseInt(countLimit, 10),
            ...actionAttrs,
            className,
            defaultGroupBy,
            defaultOrder,
            editable,
            ...trailAttrs,
            ...featuresListAttrs,
            templateDocs,
            fieldNodes,
        };
    }
}
