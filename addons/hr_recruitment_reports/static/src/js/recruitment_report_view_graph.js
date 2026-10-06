/** @odoo-module native */
import { registry } from "@web/core/registry";
import { GraphRenderer, graphView } from "@web/views/graph";

export class RecruitmentGraphRenderer extends GraphRenderer {
    getScaleOptions() {
        const scaleOptions = super.getScaleOptions();

        if ("yAxes" in scaleOptions) {
            scaleOptions.yAxes.suggestedMax = 7;
        }

        return scaleOptions;
    }
}

registry.category("views").add("recruitment_report_view_graph", {
    ...graphView,
    Renderer: RecruitmentGraphRenderer,
});
