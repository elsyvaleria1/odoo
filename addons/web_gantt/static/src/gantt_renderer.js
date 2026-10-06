/** @odoo-module native */
import { t } from "@odoo/owl";

import { GanttConnector } from "./gantt_connector.js";
import { GanttMultiSelectionButtons } from "./gantt_multi_selection_buttons.js";
import { GanttPopover } from "./gantt_popover.js";
import { GanttRendererControls } from "./gantt_renderer_controls.js";
import { GanttRendererSelection } from "./gantt_renderer_selection.js";
import { GanttRowProgressBar } from "./gantt_row_progress_bar.js";
import { GanttTimeDisplayBadge } from "./gantt_time_display_badge.js";

export class GanttRenderer extends GanttRendererSelection {
    static components = {
        GanttConnector,
        GanttRendererControls,
        GanttTimeDisplayBadge,
        GanttRowProgressBar,
        Popover: GanttPopover,
        MultiSelectionButtons: GanttMultiSelectionButtons,
    };
    static props = {
        model: t.any(),
        arch: t.any(),
        class: t.any(),
        create: t.any(),
        openDialog: t.any(),
        scrollPosition: t.any().optional(),
        multiCreateValues: t.any().optional(),
        contentRef: t.any().optional(),
        context: t.any().optional(),
    };
    static template = "web_gantt.GanttRenderer";
    static connectorCreatorTemplate = "web_gantt.GanttRenderer.ConnectorCreator";
    static headerTemplate = "web_gantt.GanttRenderer.Header";
    static pillTemplate = "web_gantt.GanttRenderer.Pill";
    static groupPillTemplate = "web_gantt.GanttRenderer.GroupPill";
    static rowContentTemplate = "web_gantt.GanttRenderer.RowContent";
    static rowHeaderTemplate = "web_gantt.GanttRenderer.RowHeader";
    static totalRowTemplate = "web_gantt.GanttRenderer.TotalRow";
    static getRowHeaderWidth = (width) => Math.round(width / (width > 768 ? 6 : 3));
}
