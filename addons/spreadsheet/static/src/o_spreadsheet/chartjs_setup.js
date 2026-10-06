/** @odoo-module native */

/**
 * @module @spreadsheet/o_spreadsheet/chartjs_setup
 *
 * Installs Chart.js — with the web client's Temporal date adapter and spreadsheet's extra
 * geo (choropleth / bubble-map) and treemap plugins — for the generated
 * `o_spreadsheet.js` bundle, which reads `globalThis.Chart` at chart-render
 * time.
 *
 * Chart.js and the plugins are real ES modules resolved through the import
 * map (`chart.js`, `chartjs-chart-geo`, `chartjs-chart-treemap`). This replaces the old
 * `web.chartjs_lib`-plus-classic-plugins bundle that o_spreadsheet relied on
 * via the global:
 *
 *   - `installChartDateAdapter` registers the date adapter onto the shared
 *     Chart (so time-scale axes format through the same date layer as the
 *     rest of the app).
 *   - The geo/treemap ESM builds, unlike their old UMD counterparts, do NOT
 *     auto-register, so we register their controllers/elements/scales onto the
 *     shared Chart explicitly below.
 *   - `o_spreadsheet.js` was generated against the UMD global, where every
 *     Chart.js export hangs off the constructor (it reads
 *     `window.Chart.BarController` to build its funnel controller,
 *     `window.Chart.BarElement` and `window.Chart._adapters`). The ESM build
 *     exposes those as named module exports instead, so we graft the module
 *     namespace onto the constructor to reproduce the UMD shape.
 *   - `globalThis.Chart = Chart` then exposes the fully plugged-in constructor
 *     to `o_spreadsheet.js`.
 *
 * This is the single, deliberate Chart global in the codebase: it exists only
 * because `o_spreadsheet.js` is a generated third-party artifact that reads the
 * global rather than importing. All other Chart consumers use the
 * `@web/core/lib/chartjs` loader.
 */

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

// Graft the named exports onto the constructor (UMD shape). Skip keys the
// class already owns (`register`, `registry`, `defaults`, ...) so genuine
// statics keep precedence over same-named module exports.
for (const [name, exported] of Object.entries(chartjs)) {
    if (!(name in Chart)) {
        Chart[name] = exported;
    }
}

globalThis.Chart = Chart;
