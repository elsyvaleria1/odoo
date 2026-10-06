// @ts-check
/** @odoo-module native */

import { installChartDateAdapter } from "@web/core/lib/chartjs_temporal_adapter";
import { makeLazyLib } from "@web/core/lib/lazy_lib";

const chartjs = makeLazyLib(
    async () => {
        const chartModule = await import("chart.js");
        installChartDateAdapter(chartModule._adapters);
        return chartModule;
    },
    {
        pick: (/** @type {any} */ module) => module.Chart,
        extra: (/** @type {any} */ module) => module.Tooltip,
        constructable: true,
    },
);

/** @type {any} */
export const Chart = chartjs.facade;

/** @type {any} */
export const Tooltip = chartjs.extraFacade;

/**
 * @returns {Promise<any>}
 */
export function loadChartJS() {
    return chartjs.load();
}
