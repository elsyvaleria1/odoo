/** @odoo-module native */
/** @ts-check */

import { getOperatorLabel } from "@web/core/tree";

import { FilterEditorFieldMatching } from "./filter_editor_field_matching.js";
import { AbstractFilterEditorSidePanel } from "./filter_editor_side_panel.js";

export class BooleanFilterEditorSidePanel extends AbstractFilterEditorSidePanel {
    static template = "spreadsheet_edition.BooleanFilterEditorSidePanel";
    static components = {
        ...AbstractFilterEditorSidePanel.components,
        FilterEditorFieldMatching,
    };

    get type() {
        return "boolean";
    }

    getOperatorLabel(operator) {
        return operator ? getOperatorLabel(operator) : "";
    }

    updateBooleanDefaultValue(ev) {
        if (ev.target.value === "") {
            this.updateDefaultValue(undefined);
        } else {
            this.updateDefaultValue({ operator: ev.target.value });
        }
    }
}
