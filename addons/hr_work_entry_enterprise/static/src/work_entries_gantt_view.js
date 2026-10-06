/** @odoo-module native */
import { hrGanttView } from "@hr_gantt/hr_gantt_view";
import { registry } from "@web/core/registry";

import { WorkEntriesGanttController } from "./work_entries_gantt_controller.js";
import { WorkEntriesGanttModel } from "./work_entries_gantt_model.js";
import { WorkEntriesGanttRenderer } from "./work_entries_gantt_renderer.js";

const viewRegistry = registry.category("views");

export const workEntriesGanttView = {
    ...hrGanttView,
    Controller: WorkEntriesGanttController,
    Renderer: WorkEntriesGanttRenderer,
    Model: WorkEntriesGanttModel,
    buttonTemplate: "hr_work_entry_enterprise.WorkEntriesGanttView.Buttons",
    searchMenuTypes: ["filter", "favorite"],
};

viewRegistry.add("work_entries_gantt", workEntriesGanttView);
