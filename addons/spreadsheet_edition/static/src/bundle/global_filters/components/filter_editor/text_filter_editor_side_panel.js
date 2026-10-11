/** @odoo-module native */
/** @ts-check */

import { components } from "@odoo/o-spreadsheet";
import { proxy } from "@odoo/owl";
import { TextFilterValue } from "@spreadsheet/global_filters/components/filter_text_value/filter_text_value";

import { FilterEditorFieldMatching } from "./filter_editor_field_matching.js";
import { AbstractFilterEditorSidePanel } from "./filter_editor_side_panel.js";

const { SelectionInput } = components;

export class TextFilterEditorSidePanel extends AbstractFilterEditorSidePanel {
    static template = "spreadsheet_edition.TextFilterEditorSidePanel";
    static components = {
        ...AbstractFilterEditorSidePanel.components,
        FilterEditorFieldMatching,
        TextFilterValue,
        SelectionInput,
    };

    setup() {
        super.setup();
        this.state = proxy({
            rangeRestriction: !!this.store.filter.rangesOfAllowedValues,
        });
    }

    get type() {
        return "text";
    }

    /**
     * @param {string[]} strings
     */
    updateTextDefaultValue(strings) {
        super.updateDefaultValue({ strings, operator: "ilike" });
    }

    toggleRangeRestriction(isChecked) {
        if (!isChecked) {
            this.onRangeChanged([]);
            this.store.update({ rangesOfAllowedValues: undefined });
        }
        this.state.rangeRestriction = isChecked;
    }

    onRangeChanged(ranges) {
        this.ranges = ranges;
    }

    onRangeConfirmed() {
        if (this.state.rangeRestriction && this.ranges.length) {
            const sheetId = this.env.model.getters.getActiveSheetId();
            const rangesOfAllowedValues = this.ranges.map((range) =>
                this.env.model.getters.getRangeFromSheetXC(sheetId, range),
            );
            this.ranges = [];
            this.store.update({ rangesOfAllowedValues });
        }
    }
}
