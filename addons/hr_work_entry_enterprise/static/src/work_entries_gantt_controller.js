/** @odoo-module native */
import { useWorkEntry } from "@hr_work_entry/views/work_entry_hook";
import {
    compareDates,
    endOf,
    startOf,
    toDateTime,
    today as getToday,
} from "@web/core/l10n/dates";
import { GanttController } from "@web_gantt/gantt_controller";

export class WorkEntriesGanttController extends GanttController {
    setup() {
        super.setup(...arguments);
        const { onRegenerateWorkEntries } = useWorkEntry({
            getEmployeeIds: () =>
                this.model.data.rows
                    .filter((r) => r.groupedByField === "employee_id")
                    .map((e) => e.resId),
            getRange: () => this.model.getRange(),
            onClose: () => this.model.fetchData({}),
        });
        this.onRegenerateWorkEntries = onRegenerateWorkEntries;
    }

    openDialog(props) {
        if (!props.resId) {
            const startDate = new Date(props["context"]["default_date_start"]);
            const stopDate = new Date(props["context"]["default_date_stop"]);
            if (
                startDate.getDate() !== stopDate.getDate() ||
                startDate.getMonth() !== stopDate.getMonth()
            ) {
                startDate.setDate(startDate.getDate() + 1);
            }
            startDate.setHours(9, 0, 0);
            props["context"]["default_date_start"] = startDate
                .toISOString()
                .replace(/T|Z/g, " ")
                .trim()
                .substring(0, 19);
            stopDate.setHours(17, 0, 0);
            props["context"]["default_date_stop"] = stopDate
                .toISOString()
                .replace(/T|Z/g, " ")
                .trim()
                .substring(0, 19);
        }

        super.openDialog(...arguments);
    }

    createAtFocusDate() {
        const { scale, globalStart, globalStop } = this.model.metaData;
        const today = toDateTime(getToday());
        if (
            scale.unit !== "day" &&
            compareDates(globalStart, endOf(today, "day")) <= 0 &&
            compareDates(today, globalStop.subtract({ milliseconds: 1 })) <= 0
        ) {
            let start;
            let stop;
            if (["week", "month"].includes(scale.unit)) {
                start = today.with({ hour: 9, minute: 0, second: 0 });
                stop = today.with({ hour: 17, minute: 0, second: 0 });
            } else {
                start = startOf(today, scale.interval);
                stop = endOf(today, scale.interval);
            }
            const context = this.model.getDialogContext({
                start,
                stop,
                withDefault: true,
            });
            this.create(context);
            return;
        }
        super.createAtFocusDate(...arguments);
    }
}
