/** @odoo-module native */
import { fetchUserFavoritesWorkEntries } from "@hr_work_entry/views/work_entry_favorites";
import { serializeDate, toISODate } from "@web/core/l10n/dates";
import { GanttModel } from "@web_gantt/gantt_model";

export class WorkEntriesGanttModel extends GanttModel {
    _getGroupedBy() {
        return ["employee_id"];
    }

    getRange() {
        const { globalStart, globalStop } = this._buildMetaData();
        return { start: globalStart, end: globalStop.subtract({ milliseconds: 1 }) };
    }

    get rangeSpan() {
        return { before: 0, count: 1 };
    }

    async resetWorkEntries(cellsInfo) {
        const cellsFormattedData = [];
        for (const { start, rowId } of cellsInfo) {
            const schedule = this.getSchedule({ start, rowId });
            cellsFormattedData.push({
                date: schedule.date,
                employee_id: schedule.employee_id,
            });
        }
        await this.orm.call(
            "wizard.hr.work.entry.regenerate",
            "regenerate_work_entries",
            [[], cellsFormattedData],
        );
        await this.fetchData();
    }

    async multiReplaceRecords(values, cellsInfo, records) {
        if (!cellsInfo.length) {
            return;
        }
        await this.orm.call("hr.work.entry", "check_modification_allowed", [
            records.map((r) => r.id),
        ]);
        const new_records = [];
        const quickreplace = values.duration < 0;
        const newly_generated_entries = [];
        for (const { start, stop, rowId } of cellsInfo) {
            const schedule = this.getSchedule({ start, stop, rowId });
            if (quickreplace) {
                const selected_cell_records = records.filter(
                    (r) =>
                        r.employee_id.id === schedule.employee_id &&
                        toISODate(r.date) === schedule.date,
                );
                const existing_duration = selected_cell_records.reduce(
                    (acc, r) => acc + r.duration,
                    0,
                );
                if (existing_duration > 0) {
                    values.duration = existing_duration;
                } else {
                    const generated_work_entry = await this.orm.call(
                        "hr.employee",
                        "generate_work_entries",
                        [schedule.employee_id, schedule.date, schedule.date, true],
                    );
                    if (generated_work_entry.length > 0) {
                        newly_generated_entries.push(generated_work_entry[0]);
                    }
                    continue;
                }
            }
            new_records.push({ ...schedule, ...values });
        }
        if (newly_generated_entries.length) {
            await this.orm.write("hr.work.entry", newly_generated_entries, {
                work_entry_type_id: values.work_entry_type_id,
            });
        }
        const created = await this.orm.create(this.metaData.resModel, new_records, {
            context: { ...this.searchParams.context, multi_create: true },
        });
        if (records.length && created) {
            await this.orm.unlink(
                this.metaData.resModel,
                records.map((r) => r.id),
            );
        }
        await this.fetchData();
    }

    /**
     * @protected
     * @override
     */
    _getDomain() {
        return this.searchParams.domain;
    }

    /**
     * @protected
     * @override
     */
    async _fetchData(metaData, additionalContext) {
        if (!this.orm.isSample) {
            const { start, end } = this.getRange();
            await this.orm.call("hr.employee", "generate_work_entries", [
                [],
                serializeDate(start),
                serializeDate(end),
            ]);
        }
        additionalContext = {
            ...additionalContext,
            gantt_start_date: serializeDate(metaData.globalStart),
            gantt_stop_date: serializeDate(metaData.globalStop),
        };
        await super._fetchData(metaData, additionalContext);
    }

    /** @override */
    _fetchCompanionData() {
        return fetchUserFavoritesWorkEntries(this.orm);
    }

    /** @override */
    _applyCompanionData(metaData, data, favorites) {
        super._applyCompanionData(...arguments);
        this.userFavoritesWorkEntries = favorites;
    }
}
