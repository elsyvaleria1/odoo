/** @odoo-module native */
/** @ts-check */

import { NumericFilterValue } from "@spreadsheet/global_filters/components/numeric_filter_value/numeric_filter_value";

import { FilterEditorFieldMatching } from "./filter_editor_field_matching.js";
import { AbstractFilterEditorSidePanel } from "./filter_editor_side_panel.js";

export class NumericFilterEditorSidePanel extends AbstractFilterEditorSidePanel {
    static template = "spreadsheet_edition.NumericFilterEditorSidePanel";
    static components = {
        ...AbstractFilterEditorSidePanel.components,
        FilterEditorFieldMatching,
        NumericFilterValue,
    };

    get type() {
        return "numeric";
    }

    /**
     * @param {number} targetValue
     */
    updateNumericDefaultValue(targetValue) {
        this.updateDefaultValue({ targetValue, operator: "=" });
    }
}
