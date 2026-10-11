/** @odoo-module native */
import { TaskGanttController } from "@project_gantt/views/task_gantt/task_gantt_controller";
import {
    compareDates,
    endOf,
    toDateTime,
    today as getToday,
} from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(TaskGanttController.prototype, {
    /**
     * @override
     */
    createAtFocusDate() {
        const { context } = this.model.searchParams;
        const { startDate, stopDate } = this.model.metaData;
        const today = toDateTime(getToday());
        if (
            context.fsm_mode &&
            compareDates(startDate, endOf(today, "day")) <= 0 &&
            compareDates(today, stopDate) <= 0
        ) {
            const stop = endOf(today, "day").add({ milliseconds: 1 });
            const context = this.model.getDialogContext({
                start: today,
                stop,
                withDefault: true,
            });
            this.create(context);
            return;
        }
        super.createAtFocusDate(...arguments);
    },
});
