// @ts-check
/** @odoo-module native */

import { onWillStart } from "@odoo/owl";
import { useColorScheme } from "@web/core/color_scheme";
import { loadChartJS } from "@web/core/lib/chartjs";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

/**
 * @param {any} component
 * @param {() => unknown[]} dependencies
 * @param {import("@web/core/utils/hooks").Ref} [canvasRef]
 * @returns {import("@web/core/utils/hooks").Ref}
 */
export function useChartCanvas(component, dependencies, canvasRef = elementRef()) {
    const scheme = useColorScheme();
    component.chart = null;

    onWillStart(() => loadChartJS());

    useLayoutEffect(
        () => {
            component.renderChart();
            return () => {
                if (component.chart) {
                    component.chart.destroy();
                    component.chart = null;
                }
            };
        },
        () => [...dependencies(), scheme.current],
    );

    return canvasRef;
}
