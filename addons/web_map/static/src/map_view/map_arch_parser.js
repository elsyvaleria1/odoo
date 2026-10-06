// @ts-check
/** @odoo-module native */
import { unique } from "@web/core/utils/collections/arrays";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { stringToOrderBy } from "@web/core/utils/order_by";
import { ViewArchParser } from "@web/views/view_arch_parser";

/**
 * @typedef {import("@web/views/ir/view_ir_schema").ViewIRNode} ViewIRNode
 * @typedef {import("@web/views/ir/view_ir_schema").MapMapAttrs} MapAttrs
 * @typedef {import("@web/views/ir/view_ir_schema").MapFieldAttrs} MapFieldAttrs
 */

export class MapArchParser extends ViewArchParser {
    /** @type {"element" | "ir"} */
    static consumes = "ir";

    /**
     * @param {ViewIRNode | Element | string} arch
     * @returns {Record<string, any>}
     */
    parse(arch) {
        /** @type {Record<string, any>} */
        const archInfo = { fieldNames: [], fieldNamesMarkerPopup: [] };
        this.visitIR(this.toIR(arch), archInfo, {
            map: this.visitMap,
            field: this.visitField,
        });
        archInfo.fieldNames = unique(archInfo.fieldNames);
        archInfo.fieldNamesMarkerPopup = unique(archInfo.fieldNamesMarkerPopup);
        return archInfo;
    }

    /**
     * @param {ViewIRNode} node
     * @param {Record<string, any>} archInfo
     */
    visitMap(node, archInfo) {
        /** @type {MapAttrs} */
        const attrs = node.attrs || {};
        archInfo.resPartnerField = attrs.res_partner ?? null;
        if (archInfo.resPartnerField) {
            archInfo.fieldNames.push(archInfo.resPartnerField);
        }

        if (attrs.limit !== undefined) {
            archInfo.limit = parseInt(attrs.limit, 10);
        }
        if (attrs.panel_title !== undefined) {
            archInfo.panelTitle = attrs.panel_title;
        }
        if (attrs.routing !== undefined) {
            archInfo.routing = exprToBoolean(attrs.routing);
        }
        if (attrs.hide_title !== undefined) {
            archInfo.hideTitle = exprToBoolean(attrs.hide_title);
        }
        if (attrs.hide_address !== undefined) {
            archInfo.hideAddress = exprToBoolean(attrs.hide_address);
        }
        if (attrs.hide_name !== undefined) {
            archInfo.hideName = exprToBoolean(attrs.hide_name);
        }
        if (!archInfo.hideName) {
            archInfo.fieldNames.push("display_name");
        }
        if (attrs.default_order !== undefined) {
            archInfo.defaultOrder = stringToOrderBy(attrs.default_order);
        }
        if (attrs.allow_resequence !== undefined) {
            archInfo.allowResequence = exprToBoolean(attrs.allow_resequence);
        }
    }

    /**
     * @param {ViewIRNode} node
     * @param {Record<string, any>} archInfo
     */
    visitField(node, archInfo) {
        /** @type {MapFieldAttrs} */
        const attrs = node.attrs || {};
        const fieldName = attrs.name;
        archInfo.fieldNames.push(fieldName);
        archInfo.fieldNamesMarkerPopup.push({
            fieldName,
            string: attrs.string ?? null,
        });
    }
}
