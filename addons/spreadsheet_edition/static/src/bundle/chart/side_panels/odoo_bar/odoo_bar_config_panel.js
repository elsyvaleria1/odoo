/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";

import { CommonOdooChartConfigPanel } from "../common/config_panel.js";

const { Checkbox } = components;

export class OdooBarChartConfigPanel extends CommonOdooChartConfigPanel {
    static template = "spreadsheet_edition.OdooBarChartConfigPanel";

    static components = {
        ...CommonOdooChartConfigPanel.components,
        Checkbox,
    };

    onUpdateStacked(stacked) {
        this.props.updateChart(this.props.chartId, {
            stacked,
        });
    }
}
