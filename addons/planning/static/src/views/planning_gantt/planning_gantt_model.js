/** @odoo-module native */
import { router } from "@web/core/browser/router";
import { Domain } from "@web/core/domain";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { pick } from "@web/core/utils/collections/objects";
import { addDuration, localStartOf } from "@web_gantt/gantt_helpers";
import { GanttModel } from "@web_gantt/gantt_model";

import { usePlanningModelActions } from "../planning_hooks.js";

const GROUPBY_COMBINATIONS = [
    "role_id",
    "role_id,resource_id",
    "role_id,department_id",
    "department_id",
    "department_id,role_id",
    "project_id",
    "project_id,department_id",
    "project_id,resource_id",
    "project_id,role_id",
];

/**
 * @typedef {import("@web_gantt/gantt_model").Data} Data
 */

/**
 * @typedef {import("@web_gantt/gantt_model").MetaData} MetaData
 */

export class PlanningGanttModel extends GanttModel {
    /**
     * @override
     */
    setup() {
        super.setup(...arguments);
        this.getHighlightIds = usePlanningModelActions({
            getHighlightPlannedIds: () =>
                this.viewContext.searchModel.highlightPlannedIds,
            getContext: () => this.viewContext.searchModel._context,
        }).getHighlightIds;
        this.isManager = null;
    }

    /**
     * @override
     */
    load(searchParams) {
        const { context, domain } = searchParams;
        this.hideOpenShift = Boolean(context.hide_open_shift);
        const displayRoleOpenShift = Boolean(context.show_role_open_shifts);
        let displayOpenShift = false;
        for (const node of domain) {
            if (
                node.length === 3 &&
                node[0] === "resource_id" &&
                ["!=", "="].includes(node[1]) &&
                node[2] === false
            ) {
                return super.load({
                    ...searchParams,
                    context: { ...context, show_job_title: true },
                });
            }
            if (
                node.length === 3 &&
                ["department_id", "manager_id", "resource_id", "job_title"].includes(
                    node[0],
                )
            ) {
                displayOpenShift = true;
            }
        }
        if (displayRoleOpenShift) {
            searchParams.domain = Domain.and([
                domain,
                [["is_users_role", "=", true]],
            ]).toList();
        } else if (displayOpenShift) {
            searchParams.domain = Domain.or([
                domain,
                "[('resource_id', '=', false)]",
            ]).toList();
        }

        let groupProm;
        if (this.isManager === null) {
            groupProm = user
                .hasGroup("planning.group_planning_manager")
                .then((result) => (this.isManager = result));
        }

        return Promise.all([
            super.load({
                ...searchParams,
                context: { ...context, show_job_title: true },
            }),
            groupProm,
        ]);
    }

    get hasMultiCreate() {
        return super.hasMultiCreate && this.isManager;
    }

    get showMultiCreateTimeRange() {
        return false;
    }

    /**
     * @override
     */
    _processProgressBars(progressBars) {
        if (!this.orm.isSample) {
            const resources = Object.values(progressBars.resource_id || []);
            for (const resource of resources) {
                if (resource.work_intervals) {
                    resource.work_intervals = resource.work_intervals.map(
                        (work_interval) => work_interval.map(deserializeDateTime),
                    );
                }
            }
        }
        return super._processProgressBars(progressBars);
    }

    /**
     * @returns {Object}
     */
    getAdditionalContext() {
        const { records } = this.data;
        const { startDate, scale, stopDate } = this.metaData;
        const defaultEmployeeIds = new Set();
        for (const record of records) {
            if (record.employee_id) {
                defaultEmployeeIds.add(record.employee_id.id);
            }
        }
        return {
            ...this.searchParams.context,
            default_start_datetime: serializeDateTime(startDate),
            default_end_datetime: serializeDateTime(stopDate),
            default_slot_ids: records.map((record) => record.id),
            scale: scale.id,
            active_domain: this.getDomain(),
            active_ids: records,
            default_employee_ids: [...defaultEmployeeIds],
        };
    }

    /**
     * @override
     */
    getDialogContext() {
        const context = super.getDialogContext(...arguments);
        delete context.show_job_title;
        delete context.highlight_planned;
        delete context.highlight_conflicting;
        if (this.metaData.scale.id === "day") {
            context.planning_keep_default_datetime = true;
        }
        return context;
    }

    /**
     * @returns {any[]}
     */
    getDomain() {
        const metaData = this._buildMetaData();
        return this._getDomain(metaData);
    }

    get rangeSpan() {
        return { before: 0, count: 1 };
    }

    /**
     * @override
     */
    getSchedule(params = {}) {
        const result = super.getSchedule(params);
        if (params.recurrence_update) {
            result.recurrence_update = params.recurrence_update;
        }
        return result;
    }

    /**
     * @override
     */
    async multiCreateRecords(multiCreateData, cellsInfo) {
        const values = await multiCreateData.record.getChanges();
        const records = [];
        if (values.template_id) {
            const [{ start_time, end_time, duration_days }] = await this.orm.read(
                "planning.slot.template",
                [values.template_id],
                ["start_time", "end_time", "duration_days"],
            );
            const days_to_hours = duration_days > 1 ? (duration_days - 1) * 24 : 0;
            for (const { rowId, start } of cellsInfo) {
                const schedule = this.getSchedule({
                    start: addDuration(start, { hours: start_time }),
                    stop: addDuration(start, { hours: end_time + days_to_hours }),
                    rowId,
                });
                records.push({ ...schedule, ...values });
            }
        }
        if (records.length) {
            await this.orm.create(this.metaData.resModel, records, {
                context: { ...this.searchParams.context, multi_create: true },
            });
            await this.fetchData();
        }
    }

    /**
     * @override
     */
    removeRedundantData(data, ids) {
        const result = super.removeRedundantData(data, ids);
        if (data.recurrence_update) {
            result.recurrence_update = data.recurrence_update;
        }
        return result;
    }

    async splitPill(start, stop, record) {
        const values = {
            start_datetime: serializeDateTime(start),
            end_datetime: serializeDateTime(stop),
        };
        const context = { planning_split_tool: true };
        const result = await this.orm.call(
            this.metaData.resModel,
            "split_pill",
            [[record.id]],
            { context, values: values },
        );
        await this.fetchData();
        return result;
    }

    /**
     * @protected
     * @param {string[]} groupedBy
     * @returns {boolean}
     */
    _allowCreateEmptyGroups(groupedBy) {
        return groupedBy.includes("resource_id");
    }

    /**
     * @protected
     * @param {string[]} groupedBy
     * @returns {boolean}
     */
    _allowedEmptyGroups(groupedBy) {
        return GROUPBY_COMBINATIONS.includes(groupedBy.join(","));
    }

    /** @override */
    _fetchCompanionData() {
        return this.getHighlightIds();
    }

    /** @override */
    _applyCompanionData(metaData, data, highlightIds) {
        super._applyCompanionData(...arguments);
        const firstRow = data.rows?.[0];
        if (firstRow?.isGroup && this.orm.isSample && !this.isClosed(firstRow.id)) {
            this.closedRows.add(firstRow.id);
        }
        this.highlightIds = highlightIds;
    }

    /**
     * @override
     */
    _generateRows(metaData, params) {
        const { groupedBy, groups, parentGroup } = params;
        if (!this.hideOpenShift) {
            if (parentGroup.length === 0) {
                if (this._allowCreateEmptyGroups(groupedBy)) {
                    groups.push({});
                }
                if (this._allowedEmptyGroups(groupedBy)) {
                    params.addOpenShifts = true;
                }
            }
            if (params.addOpenShifts && groupedBy.length === 1) {
                const fakeGroup = Object.assign({}, ...parentGroup);
                groups.push(fakeGroup);
            }
        }
        const rows = super._generateRows(...arguments);
        if (rows.length > 1) {
            rows.sort((a, b) => {
                if (a.resId && !b.resId) {
                    return 1;
                } else if (!a.resId && b.resId) {
                    return -1;
                } else {
                    return a.name.localeCompare(b.name);
                }
            });
        }
        return rows;
    }

    /**
     * @override
     */
    _getGroupedBy(metaData, searchParams) {
        let groupBy = [...searchParams.groupBy];
        if (
            !this.firstLoad &&
            searchParams.context.planning_groupby_role &&
            !groupBy.length
        ) {
            groupBy = ["role_id", "resource_id"];
        }
        return super._getGroupedBy(metaData, { ...searchParams, groupBy });
    }

    /**
     * @override
     */
    _getInitialRangeParams() {
        const urlState = router.current;
        if (urlState.date_start) {
            const focusDate = deserializeDateTime(urlState.date_start);
            let startDate;
            let stopDate;
            let rangeId;
            if (urlState.date_end) {
                const end = deserializeDateTime(urlState.date_end);
                if (localStartOf(focusDate, "week").equals(localStartOf(end, "week"))) {
                    ({ startDate, stopDate, rangeId } = this.rangeAround(
                        "week",
                        focusDate,
                    ));
                } else if (
                    localStartOf(focusDate, "month").equals(localStartOf(end, "month"))
                ) {
                    ({ startDate, stopDate, rangeId } = this.rangeAround(
                        "month",
                        focusDate,
                    ));
                } else {
                    startDate = focusDate;
                    stopDate = end;
                    rangeId = "custom";
                }
            } else {
                ({ startDate, stopDate, rangeId } = this.rangeAround(
                    "month",
                    focusDate,
                ));
            }
            return { focusDate, startDate, stopDate, rangeId };
        }
        return super._getInitialRangeParams(...arguments);
    }

    /** @override */
    _getRowName(_, groupedByField, value) {
        if (["department_id", "resource_id"].includes(groupedByField)) {
            const resId = Array.isArray(value) ? value[0] : value;
            if (!resId) {
                return _t("Open Shifts");
            }
        }
        return super._getRowName(...arguments);
    }

    /**
     * @override
     */
    _scheduleToData(schedule) {
        const allowedFields = [
            "recurrence_update",
            this.metaData.dateStartField,
            this.metaData.dateStopField,
            ...this.metaData.groupedBy,
        ];
        return pick(schedule, ...allowedFields);
    }
}
