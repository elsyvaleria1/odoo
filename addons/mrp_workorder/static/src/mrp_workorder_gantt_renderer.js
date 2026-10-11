/** @odoo-module native */
import { formatFloatTime } from "@web/core/formatters";
import { getIntersection, getUnionOfIntersections } from "@web_gantt/gantt_helpers";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

import { MRPWorkorderGanttRowProgressBar } from "./mrp_workorder_gantt_row_progress_bar.js";

export class MRPWorkorderGanttRenderer extends GanttRenderer {
    static components = {
        ...GanttRenderer.components,
        GanttRowProgressBar: MRPWorkorderGanttRowProgressBar,
    };

    addTo(pill, group) {
        const { unavailabilities } = this.model.data;
        const { start, stop } = this.getSubColumnFromColNumber(group.col);
        const { date_start: otherStart, date_end: otherStop } = pill.record;
        const interval = getIntersection(
            [start, stop.add({ seconds: 1 })],
            [otherStart, otherStop],
        );
        let pillDuration =
            interval[1].epochMilliseconds - interval[0].epochMilliseconds;
        const workcenterId = pill.record.workcenter_id && pill.record.workcenter_id.id;
        const workCenterUnavailabilities = (
            unavailabilities.workcenter_id?.[workcenterId] || []
        ).map(({ start, stop }) => [start, stop]);
        const union = getUnionOfIntersections(interval, workCenterUnavailabilities);
        for (const [otherStart, otherEnd] of union) {
            pillDuration -= otherEnd.epochMilliseconds - otherStart.epochMilliseconds;
        }
        if (union.length && !pillDuration) {
            return false;
        }
        group.pills.push(pill);
        group.aggregateValue += pillDuration;
        return true;
    }

    getGroupPillDisplayName(pill) {
        const hours = pill.aggregateValue / 3_600_000;
        return formatFloatTime(hours);
    }

    shouldComputeAggregateValues(row) {
        return row.id === "[]";
    }

    shouldMergeGroups() {
        return false;
    }
}
