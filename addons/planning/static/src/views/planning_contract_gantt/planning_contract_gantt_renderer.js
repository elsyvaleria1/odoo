/** @odoo-module native */
import { PlanningGanttRenderer } from "@planning/views/planning_gantt/planning_gantt_renderer";
import { compareDates, startOf } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(PlanningGanttRenderer.prototype, {
    /**
     * @override
     */
    ganttCellAttClass(row, column) {
        return {
            ...super.ganttCellAttClass(...arguments),
            o_resource_has_no_working_periods: !this._resourceHasWorkingPeriods(
                column,
                row,
            ),
        };
    },

    /**
     * @param {number} column - Column index
     * @param {Row} row - Row Object
     */
    _resourceHasWorkingPeriods(column, row) {
        const { workingPeriods } = this.model.data;
        if (!workingPeriods) {
            return true;
        }
        const resourceId = Object.assign({}, ...JSON.parse(row.id)).resource_id?.[0];
        const periods = workingPeriods[resourceId];
        if (periods?.length) {
            const { interval } = this.model.metaData.scale;
            const left = startOf(column.start, interval);
            const right = startOf(column.stop, interval);
            return periods.some(
                ({ start, end }) =>
                    compareDates(startOf(start, interval), left) <= 0 &&
                    (!end || compareDates(startOf(end, interval), right) >= 0),
            );
        }
        return periods === undefined;
    },
});
