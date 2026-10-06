/** @odoo-module native */
import { provideSpreadsheetEnv } from "@spreadsheet/hooks";
import { AbstractSpreadsheetAction } from "@spreadsheet_edition/bundle/actions/abstract_spreadsheet_action";
import { registry } from "@web/core/registry";

import { useSpreadsheetQualityControlExtension } from "../quality_spreadsheet_extension.js";

export class QualitySpreadsheetTemplateAction extends AbstractSpreadsheetAction {
    static template = "quality_control_spreadsheet.QualitySpreadsheetTemplateAction";
    static path = "quality-spreadsheet-template";

    resModel = "quality.spreadsheet.template";

    setup() {
        super.setup();
        provideSpreadsheetEnv({
            makeCopy: this.makeCopy.bind(this),
        });

        useSpreadsheetQualityControlExtension();
    }

    onSpreadsheetLeftUpdateVals() {
        const values = super.onSpreadsheetLeftUpdateVals();
        const resultCellString = this.model.getters.getQualityCheckResultCellString();
        if (resultCellString !== this.data.quality_check_cell) {
            values.check_cell = resultCellString;
        }
        return values;
    }

    getModelConfig() {
        const config = super.getModelConfig();
        config.custom.qualitySuccessCell = this.data.quality_check_cell;
        return config;
    }
}

registry
    .category("actions")
    .add("action_quality_spreadsheet_template", QualitySpreadsheetTemplateAction, {
        force: true,
    });
