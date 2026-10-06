/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { ModelFieldSelector } from "@web/components/model_field_selector";
import { useDebugMode } from "@web/core/debug/debug_context";

import { sortModelFieldSelectorFields } from "../../../helpers/misc.js";
import { FilterFieldOffset } from "../filter_field_offset.js";

/**
 * @typedef {import("@spreadsheet").FieldMatching} FieldMatching
 */

export class FilterEditorFieldMatching extends Component {
    static template = "spreadsheet_edition.FilterEditorFieldMatching";
    static components = {
        ModelFieldSelector,
        FilterFieldOffset,
    };

    static props = {
        fieldMatchings: t.array(),
        selectField: t.function(),
        filterModelFieldSelectorField: t.function(),
        onOffsetSelected: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }

    sortModelFieldSelectorFields = sortModelFieldSelectorFields;

    /**
     *
     * @param {FieldMatching} fieldMatch
     * @returns {string}
     */
    getModelField(fieldMatch) {
        if (!fieldMatch || !fieldMatch.chain) {
            return "";
        }
        return fieldMatch.chain;
    }
}
