import { expect, getFixture, test } from "@odoo/hoot";
import { Model } from "@odoo/o-spreadsheet";
import {
    createBasicChart,
    setCellContent,
} from "@spreadsheet/../tests/helpers/commands";
import { defineSpreadsheetModels } from "@spreadsheet/../tests/helpers/data";

defineSpreadsheetModels();

function createDateLineChart() {
    const model = new Model();
    const rows = [
        ["1/1/2022", "10"],
        ["1/2/2022", "20"],
        ["1/3/2022", "15"],
        ["1/5/2022", "30"],
    ];
    rows.forEach(([date, value], index) => {
        setCellContent(model, `A${index + 1}`, date);
        setCellContent(model, `B${index + 1}`, value);
    });
    createBasicChart(model, "chartId", {
        type: "line",
        labelRange: "A1:A4",
        dataSets: [{ dataRange: "B1:B4" }],
        dataSetsHaveTitle: false,
        labelsAsText: false,
    });
    return model;
}

test("a line chart over date labels gets a time axis", () => {
    const model = createDateLineChart();
    const { chartJsConfig } = model.getters.getChartRuntime("chartId");
    expect(chartJsConfig.options.scales.x.type).toBe("time");
    expect(chartJsConfig.options.scales.x.time).toEqual({
        parser: "M/d/yyyy",
        displayFormats: { day: "M/d/yyyy" },
        unit: "day",
        tooltipFormat: "M/d/yyyy",
    });
});

test("Chart.js lays a time axis out through the date adapter", () => {
    const model = createDateLineChart();
    const { chartJsConfig } = model.getters.getChartRuntime("chartId");
    const canvas = document.createElement("canvas");
    getFixture().append(canvas);
    const chart = new window.Chart(canvas, {
        ...chartJsConfig,
        options: { ...chartJsConfig.options, animation: false, responsive: false },
    });
    try {
        expect(chart.scales.x.ticks.map((tick) => tick.label)).toEqual([
            "1/1/2022",
            "1/2/2022",
            "1/3/2022",
            "1/4/2022",
            "1/5/2022",
        ]);
        expect(chart.scales.x.getLabelForValue(chart.scales.x.min)).toBe("1/1/2022");
    } finally {
        chart.destroy();
    }
});
