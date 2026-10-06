/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";

import { CommonOdooChartConfigPanel } from "../common/config_panel.js";

const { Checkbox } = components;

export class OdooLineChartConfigPanel extends CommonOdooChartConfigPanel {
    static template = "spreadsheet_edition.OdooLineChartConfigPanel";
    static components = {
        ...CommonOdooChartConfigPanel.components,
        Checkbox,
    };

    get stackedLabel() {
        const definition = this.props.definition;
        return definition.fillArea
            ? this.chartTerms.StackedAreaChart
            : this.chartTerms.StackedLineChart;
    }

    onUpdateStacked(stacked) {
        this.props.updateChart(this.props.chartId, {
            stacked,
        });
    }
    onUpdateCumulative(cumulative) {
        this.props.updateChart(this.props.chartId, {
            cumulative,
        });
    }
    onUpdateCumulatedStart(cumulatedStart) {
        this.props.updateChart(this.props.chartId, {
            cumulatedStart,
        });
    }
}
