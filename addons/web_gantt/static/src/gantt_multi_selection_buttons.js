/** @odoo-module native */
import { t } from "@odoo/owl";
import { MultiSelectionButtons } from "@web/views/view_components";

export class GanttMultiSelectionButtons extends MultiSelectionButtons {
    static template = "web_gantt.GanttMultiSelectionButtons";
    static props = {
        reactive: t.object({
            ...MultiSelectionButtons.props.reactive.toShape(),
            onPlan: t.function().optional(),
        }),
    };
}
