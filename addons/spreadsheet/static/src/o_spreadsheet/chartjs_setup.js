/** @odoo-module native */

import { installChartDateAdapter } from "@web/core/lib/chartjs_temporal_adapter";

import * as chartjs from "chart.js";
import {
    BubbleMapController,
    ChoroplethController,
    ColorLogarithmicScale,
    ColorScale,
    GeoFeature,
    ProjectionScale,
    SizeLogarithmicScale,
    SizeScale,
} from "chartjs-chart-geo";
import { TreemapController, TreemapElement } from "chartjs-chart-treemap";

const { Chart } = chartjs;

installChartDateAdapter(chartjs._adapters);

Chart.register(
    ChoroplethController,
    BubbleMapController,
    GeoFeature,
    ColorScale,
    ColorLogarithmicScale,
    ProjectionScale,
    SizeScale,
    SizeLogarithmicScale,
    TreemapController,
    TreemapElement,
);

for (const [name, exported] of Object.entries(chartjs)) {
    if (!(name in Chart)) {
        Chart[name] = exported;
    }
}

globalThis.Chart = Chart;
