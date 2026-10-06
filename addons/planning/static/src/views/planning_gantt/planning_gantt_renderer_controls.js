/** @odoo-module native */
import { t } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { GanttRendererControls } from "@web_gantt/gantt_renderer_controls";

export class PlanningGanttRendererControls extends GanttRendererControls {
    static props = {
        ...GanttRendererControls.props,
        duplicateToolHelperReactive: t.any(),
    };
    static toolbarContentTemplate =
        "planning.PlanningGanttRendererControls.ToolbarContent";

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}
