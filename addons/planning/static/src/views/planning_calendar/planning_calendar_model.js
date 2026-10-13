/** @odoo-module native */
import { endOf } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { CalendarModel } from "@web/views/calendar";

import { usePlanningModelActions } from "../planning_hooks.js";
import { planningAskRecurrenceUpdate } from "./planning_ask_recurrence_update/planning_ask_recurrence_update_hook.js";

/**
 * @param {Temporal.ZonedDateTime} date
 * @param {number} hours
 */
function addHours(date, hours) {
    return date.add({ milliseconds: Math.round(hours * 3_600_000) });
}

export class PlanningCalendarModel extends CalendarModel {
    static services = [...CalendarModel.services, "dialog", "orm"];

    setup(params, services) {
        super.setup(...arguments);
        this.dialog = services.dialog;
        this.getHighlightIds = usePlanningModelActions({
            getHighlightPlannedIds: () =>
                this.viewContext.searchModel.highlightPlannedIds,
            getContext: () => this.viewContext.searchModel._context,
        }).getHighlightIds;
        this.meta.scale = this.viewContext.isSmall ? "day" : this.meta.scale;
        this.isManager = null;
    }

    async load() {
        let groupProm;
        if (this.isManager === null) {
            groupProm = user
                .hasGroup("planning.group_planning_manager")
                .then((result) => (this.isManager = result));
        }
        return Promise.all([super.load(...arguments), groupProm]);
    }

    get hasMultiCreate() {
        return super.hasMultiCreate && this.isManager;
    }

    get showMultiCreateTimeRange() {
        return false;
    }

    get defaultFilterLabel() {
        return _t("Open Shifts");
    }

    /**
     * @override
     */
    addFilterFields(record, filterInfo) {
        if (filterInfo.fieldName === "resource_id") {
            return {
                colorIndex:
                    record.rawRecord.resource_type &&
                    record.rawRecord.resource_type !== "human"
                        ? record.rawRecord["resource_color"]
                        : "",
                resourceType: record.rawRecord["resource_type"],
            };
        }
        return {
            ...super.addFilterFields(record, filterInfo),
            resourceType: record.rawRecord["resource_type"],
        };
    }

    /**
     * @override
     */
    async loadRecords(data) {
        this.highlightIds = await this.getHighlightIds();
        return await super.loadRecords(data);
    }

    /**
     * @override
     */
    async updateRecord(record) {
        const rec = this.records[record.id];
        if (rec.rawRecord.repeat) {
            const recurrenceUpdate = await planningAskRecurrenceUpdate(this.dialog);
            if (!recurrenceUpdate) {
                return this.notify();
            }
            record.recurrenceUpdate = recurrenceUpdate;
        }
        return await super.updateRecord(...arguments);
    }

    /**
     * @override
     */
    buildRawRecord(partialRecord, options = {}) {
        if (options.batch_create_calendar) {
            let days_to_hours = 0;
            if (options.schedule[0]["duration_days"] > 1) {
                days_to_hours = (options.schedule[0]["duration_days"] - 1) * 24;
            }
            partialRecord.end = addHours(
                partialRecord.start,
                options.schedule[0]["end_time"] + days_to_hours,
            );
            partialRecord.start = addHours(
                partialRecord.start,
                options.schedule[0]["start_time"],
            );
        }
        const result = super.buildRawRecord(partialRecord, options);
        if (partialRecord.recurrenceUpdate) {
            result.recurrence_update = partialRecord.recurrenceUpdate;
        }
        return result;
    }

    /**
     * @override
     */
    makeFilterDynamic(filterInfo, previousFilter, fieldName, rawFilter, rawColors) {
        return {
            ...super.makeFilterDynamic(
                filterInfo,
                previousFilter,
                fieldName,
                rawFilter,
                rawColors,
            ),
            resourceType: rawFilter["resourceType"],
            colorIndex: rawFilter["colorIndex"],
        };
    }

    /**
     * @override
     */
    makeContextDefaults(rawRecord) {
        const context = super.makeContextDefaults(...arguments);
        if (["day", "week"].includes(this.meta.scale)) {
            context["planning_keep_default_datetime"] = true;
        }
        return context;
    }

    /**
     * @override
     */
    getAllDayDates(start, end) {
        return [start.startOfDay(), endOf(end, "day")];
    }

    /**
     * @override
     */
    async multiCreateRecords(multiCreateData, dates) {
        if (!dates.length) {
            await this.load();
            return [];
        }
        const values = await multiCreateData.record.getChanges();
        if (values.template_id) {
            const schedule = await this.orm.read(
                "planning.slot.template",
                [values["template_id"]],
                ["start_time", "end_time", "duration_days"],
            );
            const records = [];
            const [section] = this.filterSections;
            for (const date of dates) {
                const rawRecord = this.buildRawRecord(
                    { start: date },
                    { batch_create_calendar: true, schedule: schedule },
                );
                for (const filter of section.filters) {
                    if (filter.active && filter.type === "record") {
                        records.push({
                            ...rawRecord,
                            ...values,
                            [section.fieldName]: filter.value,
                        });
                    }
                }
            }
            if (records.length) {
                const createdRecords = await this.orm.call(
                    this.meta.resModel,
                    "create_batch_from_calendar",
                    [[], records],
                );
                await this.load();
                return createdRecords;
            }
            return [];
        }
    }

    /**
     * @override
     */
    fetchFilters(resModel, fieldNames) {
        return this.orm.call(resModel, "get_or_create_calendar_filters", [
            [],
            user.userId,
            fieldNames,
        ]);
    }

    /**
     * @override
     */
    makeFilterRecord(filterInfo, previousFilter, rawRecord) {
        const filterRecord = super.makeFilterRecord(...arguments);
        if (!filterRecord.value) {
            filterRecord.canRemove = false;
            filterRecord.label = _t("Open Shifts");
        }
        filterRecord.resourceType = rawRecord.resource_type;
        return filterRecord;
    }

    async loadFilters(data) {
        const loadedFilters = await super.loadFilters(data);
        if (
            !Object.keys(this.data.filterSections).length &&
            loadedFilters.sections.resource_id?.filters
        ) {
            loadedFilters.sections.resource_id.filters[0].active = true;
        }
        return loadedFilters;
    }
}
