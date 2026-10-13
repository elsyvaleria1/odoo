/** @odoo-module native */
import { markRaw, toRaw } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";
import { formatFloatTime, formatPercentage } from "@web/core/formatters";
import {
    compareDates,
    deserializeDate,
    deserializeDateTime,
    now,
    serializeDate,
    serializeDateTime,
    toDateTime,
    toISO,
} from "@web/core/l10n/dates";
import { x2ManyCommands } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { unique } from "@web/core/utils/collections/arrays";
import { pick } from "@web/core/utils/collections/objects";
import { KeepLast, Mutex, SupersededError } from "@web/core/utils/concurrency";
import { Model } from "@web/model/model";
import { parseServerValue } from "@web/model/relational_model";
import { useGanttContext } from "@web_gantt/gantt_context";

import { addDuration, localStartOf } from "./gantt_helpers.js";
import {
    customRangeAround,
    getScaleForCustomRange,
    normalizeRange,
} from "./gantt_ranges.js";

/**
 * @typedef {Temporal.ZonedDateTime} DateTime
 * @typedef {`[{${string}}]`} RowId
 * @typedef {import("./gantt_arch_parser").Scale} Scale
 * @typedef {import("./gantt_arch_parser").ScaleId} ScaleId
 * @typedef ConsolidationParams
 * @property {string} excludeField
 * @property {string} field
 * @property {string} [maxField]
 * @property {string} [maxValue]
 * @typedef Data
 * @property {Record<string, any>[]} records
 * @property {Row[]} rows
 * @typedef Field
 * @property {string} name
 * @property {string} type
 * @property {[any, string][]} [selection]
 * @typedef MetaData
 * @property {ConsolidationParams} consolidationParams
 * @property {string} dateStartField
 * @property {string} dateStopField
 * @property {string[]} decorationFields
 * @property {ScaleId} defaultRange
 * @property {string} dependencyField
 * @property {boolean} dependencyEnabled
 * @property {Scale} scale
 * @property {Record<string, import("./gantt_arch_parser").Range>} ranges
 * @property {DateTime} startDate
 * @property {DateTime} stopDate
 * @property {string} defaultRescheduleMethod
 * @property {string} rescheduleMethod
 * @property {Object[]} rescheduleMethods
 * @typedef ProgressBar
 * @property {number} value_formatted
 * @property {number} max_value_formatted
 * @property {number} ratio
 * @property {string} warning
 * @typedef Row
 * @property {RowId} id
 * @property {boolean} consolidate
 * @property {boolean} fromServer
 * @property {string[]} groupedBy
 * @property {string} groupedByField
 * @property {number} groupLevel
 * @property {string} name
 * @property {number[]} recordIds
 * @property {ProgressBar} [progressBar]
 * @property {number | false} resId
 * @property {Row[]} [rows]
 */

function serializeDateForField(field, date) {
    return field.type === "date" ? serializeDate(date) : serializeDateTime(date);
}

function mapByFieldAndResId(source, mapValue) {
    const result = {};
    for (const fieldName in source) {
        result[fieldName] = {};
        const { warning, ...byResId } = source[fieldName];
        for (const [resId, value] of Object.entries(byResId)) {
            result[fieldName][resId] = mapValue(value, warning);
        }
    }
    return result;
}

/**
 * @param {Record<string, Field>} fields
 * @param {Record<string, any>} values
 */
export function parseServerValues(fields, values) {
    /** @type {Record<string, any>} */
    const parsedValues = {};
    if (!values) {
        return parsedValues;
    }
    for (const fieldName in values) {
        parsedValues[fieldName] = parseServerValue(
            fields[fieldName],
            values[fieldName],
        );
    }
    return parsedValues;
}

const log = makeLogger("gantt.model");

export class GanttModel extends Model {
    static useViewContext() {
        const viewContext = super.useViewContext();
        viewContext.ganttContext = useGanttContext();
        return viewContext;
    }

    static services = ["notification"];

    /** @returns {Data} */
    get data() {
        void this.updateEpoch;
        return toRaw(this)._data;
    }

    set data(data) {
        toRaw(this)._data = data && markRaw(data);
    }

    /** @returns {MetaData} */
    get metaData() {
        void this.updateEpoch;
        return toRaw(this)._metaData;
    }

    set metaData(metaData) {
        toRaw(this)._metaData = metaData;
    }

    setup(params, services) {
        this.notification = services.notification;

        this.data = {};
        this.metaData = { ...params.metaData };
        this.displayParams = { ...params.displayParams };

        this.searchParams = null;

        /** @type {Set<RowId>} */
        this.closedRows = markRaw(new Set());

        this.keepLast = new KeepLast({ rejectSuperseded: true });
        this.mutex = new Mutex();
        /** @type {MetaData | null} */
        this._nextMetaData = null;
    }

    /**
     * @param {SearchParams} searchParams
     */
    async load(searchParams) {
        this.searchParams = searchParams;

        const metaData = this._buildMetaData();
        log.pipeline("load", () => ({
            resModel: metaData.resModel,
            scale: metaData.scale?.id,
            rangeId: metaData.rangeId,
            groupBy: searchParams.groupBy,
            domain: searchParams.domain,
        }));

        const params = {
            groupedBy: this._getGroupedBy(metaData, searchParams),
            pagerOffset: 0,
        };

        if (!metaData.scale || !metaData.startDate || !metaData.stopDate) {
            Object.assign(
                params,
                this._getInitialRangeParams(this._buildMetaData(params), searchParams),
            );
        }

        if (this.metaData.dependencyEnabled) {
            Object.assign(
                params,
                this._getInitialRescheduleMethod(this._buildMetaData(params)),
            );
        }

        await this._fetchData(this._buildMetaData(params));
    }

    get hasMultiCreate() {
        return (
            !!this.metaData.multiCreateView &&
            !this.viewContext.isSmall &&
            this.displayParams.displayMode === "dense" &&
            this.metaData.scale.interval === "day"
        );
    }

    get showMultiCreateTimeRange() {
        return !this.dateStartFieldIsDate() && !this.dateStopFieldIsDate();
    }

    collapseRows() {
        const collapse = (rows) => {
            for (const row of rows) {
                this.closedRows.add(row.id);
                if (row.rows) {
                    collapse(row.rows);
                }
            }
        };
        collapse(this.data.rows);
        this.notify();
    }

    /**
     * @param {number} id
     * @param {Record<string, any>} schedule
     * @param {(result: any) => any} [callback]
     */
    copy(id, schedule, callback) {
        const { resModel } = this.metaData;
        const { context } = this.searchParams;
        const data = this._scheduleToData(schedule);
        return this.mutex.exec(async () => {
            const result = await this.orm.call(resModel, "copy", [[id]], {
                context,
                default: data,
            });
            if (callback) {
                callback(result[0]);
            }
            this.fetchData();
            return result[0];
        });
    }

    /**
     * @param {number} masterId
     * @param {number} slaveId
     */
    async createDependency(masterId, slaveId) {
        const { dependencyField, resModel } = this.metaData;
        log.logic("createDependency", () => ({
            resModel,
            dependencyField,
            masterId,
            slaveId,
        }));
        const writeCommand = {
            [dependencyField]: [x2ManyCommands.link(masterId)],
        };
        await this.mutex.exec(() => this.orm.write(resModel, [slaveId], writeCommand));
        await this.fetchData();
    }

    dateStartFieldIsDate(metaData = this.metaData) {
        return metaData?.fields[metaData.dateStartField].type === "date";
    }

    dateStopFieldIsDate(metaData = this.metaData) {
        return metaData?.fields[metaData.dateStopField].type === "date";
    }

    expandRows() {
        this.closedRows.clear();
        this.notify();
    }

    get rowsAreExpanded() {
        return this.closedRows.size === 0;
    }

    async fetchData(params) {
        await this._fetchData(this._buildMetaData(params));
        this.useSampleModel = false;
        this.notify();
    }

    /**
     * @param {Object} params
     * @param {RowId} [params.rowId]
     * @param {DateTime} [params.start]
     * @param {DateTime} [params.stop]
     * @param {boolean} [params.withDefault]
     * @returns {Record<string, any>}
     */
    getDialogContext(params) {
        /** @type {Record<string, any>} */
        const context = { ...this.getSchedule(params) };

        if (params.withDefault) {
            const { dateStartField, dateStopField } = this.metaData;
            for (const k in context) {
                context[`default_${k}`] = context[k];
                if (![dateStartField, dateStopField].includes(k)) {
                    context[`search_default_${k}`] = context[k];
                }
            }
        }

        return Object.assign({}, this.searchParams.context, context);
    }

    get rangeSpan() {
        return { before: 1, count: 3 };
    }

    rangeAround(rangeId, date) {
        const { before, count } = this.rangeSpan;
        const startDate = addDuration(localStartOf(date, rangeId), {
            [rangeId]: -before,
        });
        const stopDate = addDuration(startDate, { [rangeId]: count }).subtract({
            days: 1,
        });
        return { focusDate: date, startDate, stopDate, rangeId };
    }

    /**
     * @param {Object} params
     * @param {RowId} [params.rowId]
     * @param {DateTime} [params.start]
     * @param {DateTime} [params.stop]
     * @returns {Record<string, any>}
     */
    getSchedule({ rowId, start, stop } = {}) {
        const { dateStartField, dateStopField, fields, groupedBy } = this.metaData;

        /** @type {Record<string, any>} */
        const schedule = {};

        if (start) {
            schedule[dateStartField] = serializeDateForField(
                fields[dateStartField],
                start,
            );
        }
        if (stop && dateStartField !== dateStopField) {
            schedule[dateStopField] = serializeDateForField(
                fields[dateStopField],
                stop,
            );
        }
        if (rowId) {
            const group = Object.assign({}, ...JSON.parse(rowId));
            for (const fieldName of groupedBy) {
                if (fieldName in group) {
                    const value = group[fieldName];
                    if (Array.isArray(value)) {
                        const { type } = fields[fieldName];
                        schedule[fieldName] =
                            type === "many2many" ? [value[0]] : value[0];
                    } else {
                        schedule[fieldName] = value;
                    }
                }
            }
        }

        return schedule;
    }

    /**
     * @override
     * @returns {boolean}
     */
    hasData() {
        return Boolean(this.data.records.length);
    }

    /**
     * @param {RowId} rowId
     * @returns {boolean}
     */
    isClosed(rowId) {
        return this.closedRows.has(rowId);
    }

    async multiCreateRecords(multiCreateData, cellsInfo) {
        log.logic("multiCreateRecords", () => ({
            cells: cellsInfo.length,
            fields: Object.keys(multiCreateData || {}),
        }));
        if (!cellsInfo.length) {
            return;
        }
        const records = [];
        const values = await multiCreateData.record.getChanges();
        const timeRange = multiCreateData.timeRange;
        for (const { start, stop, rowId } of cellsInfo) {
            const schedule = this.getSchedule(
                timeRange
                    ? {
                          start: start.with(timeRange.start.toObject()),
                          stop: start.with(timeRange.end.toObject()),
                          rowId,
                      }
                    : { start, stop, rowId },
            );
            records.push({ ...schedule, ...values });
        }
        await this.orm.create(this.metaData.resModel, records, {
            context: { ...this.searchParams.context, multi_create: true },
        });
        await this.fetchData();
    }

    async unlinkRecords(ids) {
        log.logic("unlinkRecords", () => ({ ids }));
        if (!ids.length) {
            return;
        }
        await this.orm.unlink(this.metaData.resModel, ids);
        await this.fetchData();
    }

    /**
     * @param {number} masterId
     * @param {number} slaveId
     */
    async removeDependency(masterId, slaveId) {
        const { dependencyField, resModel } = this.metaData;
        const writeCommand = {
            [dependencyField]: [x2ManyCommands.unlink(masterId)],
        };
        await this.mutex.exec(() => this.orm.write(resModel, [slaveId], writeCommand));
        await this.fetchData();
    }

    /**
     * @template {Record<string, any>} T
     * @param {T} data
     * @param {number[]} ids
     * @returns {Partial<T>}
     */
    removeRedundantData(data, ids) {
        const idSet = new Set(ids);
        const records = this.data.records.filter((rec) => idSet.has(rec.id));
        if (!records.length) {
            return data;
        }

        /**
         *
         * @param {Record<string, any>} record
         * @param {Field} field
         */
        const isSameValue = (record, { name, type }) => {
            const recordValue = record[name];
            let newValue = data[name];
            if (Array.isArray(newValue)) {
                [newValue] = newValue;
            }
            if (type === "many2one") {
                return recordValue.id === newValue;
            } else if (type === "one2many") {
                return recordValue[0] === newValue;
            } else if (type === "many2many") {
                return recordValue.includes(newValue);
            } else if (type === "date" || type === "datetime") {
                return serializeDateForField({ type }, recordValue) === newValue;
            } else {
                return recordValue === newValue;
            }
        };

        /** @type {Partial<T>} */
        const trimmed = { ...data };

        for (const fieldName in data) {
            const field = this.metaData.fields[fieldName];
            if (records.every((rec) => isSameValue(rec, field))) {
                delete trimmed[fieldName];
            }
        }

        return trimmed;
    }

    _getRescheduleData(ids, schedule) {
        if (!Array.isArray(ids)) {
            ids = [ids];
        }
        const allData = this._scheduleToData(schedule);
        return [
            ids,
            this.removeRedundantData(allData, ids),
            this._getRescheduleContext(),
        ];
    }

    /**
     * @param {number | number[]} ids
     * @param {Record<string, any>} schedule
     * @param {(result: any) => any} [callback]
     */
    async reschedule(ids, schedule, callback) {
        let data, context;
        [ids, data, context] = this._getRescheduleData(ids, schedule);
        log.logic("reschedule", () => ({
            ids,
            data,
            method: this.displayParams?.rescheduleMethod,
        }));
        return this.mutex.exec(async () => {
            try {
                const result = await this._reschedule(ids, data, context);
                if (callback) {
                    await callback(result);
                }
            } finally {
                this.fetchData();
            }
        });
    }

    async _reschedule(ids, data, context) {
        return this.orm.write(this.metaData.resModel, ids, data, {
            context,
        });
    }

    async rescheduleAccordingToDependency(
        ids,
        schedule,
        rescheduleAccordingToDependencyCallback,
    ) {
        const {
            dateStartField,
            dateStopField,
            dependencyField,
            dependencyInvertedField,
            resModel,
        } = this.metaData;

        let data;
        [ids, data] = this._getRescheduleData(ids, schedule);

        return await this.mutex.exec(async () => {
            try {
                const result = await this.orm.call(resModel, "web_gantt_reschedule", [
                    data,
                    this.metaData.rescheduleMethod,
                    ids,
                    dependencyField,
                    dependencyInvertedField,
                    dateStartField,
                    dateStopField,
                ]);
                if (rescheduleAccordingToDependencyCallback) {
                    await rescheduleAccordingToDependencyCallback(result);
                }
            } finally {
                this.fetchData();
            }
        });
    }

    /**
     * @param {string} rowId
     */
    toggleRow(rowId) {
        log.logic("toggleRow", () => ({ rowId, closed: this.isClosed(rowId) }));
        if (this.isClosed(rowId)) {
            this.closedRows.delete(rowId);
        } else {
            this.closedRows.add(rowId);
        }
        this.notify();
    }

    toggleDisplayMode() {
        log.logic("toggleDisplayMode", () => ({
            from: this.displayParams.displayMode,
        }));
        this.displayParams.displayMode =
            this.displayParams.displayMode === "dense" ? "sparse" : "dense";
        this.closedRows.clear();
        this.notify();
    }

    async updatePagerParams({ limit, offset }) {
        await this.fetchData({ pagerLimit: limit, pagerOffset: offset });
    }

    /**
     * @protected
     * @param {Object} params
     * @param {DateTime} [params.focusDate]
     * @param {DateTime} [params.startDate]
     * @param {DateTime} [params.stopDate]
     * @param {string[]} [params.groupedBy]
     * @param {ScaleId} [params.rangeId]
     * @returns {MetaData}
     */
    _buildMetaData(params = {}) {
        this._nextMetaData = { ...(this._nextMetaData || this.metaData) };

        if (params.groupedBy) {
            this._nextMetaData.groupedBy = params.groupedBy;
        }
        if (params.focusDate) {
            this._nextMetaData.focusDate = params.focusDate;
        }
        if (params.startDate) {
            this._nextMetaData.startDate = params.startDate;
        }
        if (params.stopDate) {
            this._nextMetaData.stopDate = params.stopDate;
        }
        if (params.rangeId) {
            this._nextMetaData.rangeId = params.rangeId;
            if (this._nextMetaData.rangeId !== "custom") {
                this._nextMetaData.scale =
                    this._nextMetaData.ranges[params.rangeId].scale;
            }
        }
        if (params.rescheduleMethod) {
            browser.localStorage.setItem(
                this._getRescheduleMethodLocalStorageKey(),
                params.rescheduleMethod,
            );
            this._nextMetaData.rescheduleMethod = params.rescheduleMethod;
        }

        if ("pagerLimit" in params) {
            this._nextMetaData.pagerLimit = params.pagerLimit;
        }
        if ("pagerOffset" in params) {
            this._nextMetaData.pagerOffset = params.pagerOffset;
        }

        if ("rangeId" in params || "startDate" in params || "stopDate" in params) {
            if (!("pagerOffset" in params)) {
                this._nextMetaData.pagerOffset = 0;
            }
            if (this._nextMetaData.rangeId === "custom") {
                this._nextMetaData.scale = getScaleForCustomRange(this._nextMetaData);
            }
            Object.assign(
                this._nextMetaData,
                normalizeRange({
                    startDate: this._nextMetaData.startDate,
                    stopDate: this._nextMetaData.stopDate,
                    interval: this._nextMetaData.scale.interval,
                    focusDate: params.currentFocusDate,
                }),
            );
        }

        return this._nextMetaData;
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {Object} [additionalContext]
     */
    async _fetchData(metaData, additionalContext) {
        const {
            globalStart,
            globalStop,
            groupedBy,
            pagerLimit,
            pagerOffset,
            resModel,
            scale,
        } = metaData;
        const context = {
            ...this.searchParams.context,
            group_by: groupedBy,
            ...additionalContext,
        };
        const domain = this._getDomain(metaData);
        const fields = this._getFields(metaData);
        const specification = {};
        for (const fieldName of fields) {
            specification[fieldName] = {};
            if (metaData.fields[fieldName]?.type === "many2one") {
                specification[fieldName].fields = { display_name: {} };
            }
        }

        let ganttData;
        let companion;
        const endFetch = log.perf(`get_gantt_data ${resModel}`);
        log.pipeline("fetchData", () => ({
            resModel,
            scale: scale.unit,
            groupedBy,
            start: globalStart && toISO(globalStart),
            stop: globalStop && toISO(globalStop),
            limit: pagerLimit,
            offset: pagerOffset,
            fields: fields.length,
        }));
        try {
            [ganttData, companion] = await this.keepLast.add(
                Promise.all([
                    this.orm.call(resModel, "get_gantt_data", [], {
                        domain,
                        groupby: groupedBy,
                        read_specification: specification,
                        scale: scale.unit,
                        start_date: serializeDateTime(globalStart),
                        stop_date: serializeDateTime(globalStop),
                        unavailability_fields: this._getUnavailabilityFields(metaData),
                        progress_bar_fields: this._getProgressBarFields(metaData),
                        context,
                        limit: pagerLimit,
                        offset: pagerOffset,
                    }),
                    this._fetchCompanionData(metaData, context),
                ]),
            );
        } catch (error) {
            if (error instanceof SupersededError) {
                endFetch({ superseded: true });
                return;
            }
            this._nextMetaData = null;
            endFetch({ failed: true });
            throw error;
        }

        const { length, groups, records, progress_bars, unavailabilities } = ganttData;
        endFetch({ records: records.length, groups: groups.length, length });

        groups.forEach((g) => (g.fromServer = true));

        const data = { count: length };

        data.records = this._parseServerData(metaData, records);
        data.rows = this._generateRows(metaData, {
            groupedBy,
            groups,
            parentGroup: [],
        });
        data.unavailabilities = this._processUnavailabilities(unavailabilities);
        data.progressBars = this._processProgressBars(progress_bars);

        this._processGanttData(metaData, data, ganttData);
        log.pipeline("processed", () => ({
            rows: data.rows.length,
            records: Object.keys(data.records).length,
            unavailabilities: Object.keys(data.unavailabilities || {}).length,
        }));

        if (JSON.stringify(this.metaData.groupedBy) !== JSON.stringify(groupedBy)) {
            this.closedRows.clear();
        }
        this._applyCompanionData(metaData, data, companion);
        this.data = data;
        this.metaData = metaData;
        this._nextMetaData = null;
        browser.localStorage.setItem(this._getLocalStorageKey(), metaData.rangeId);
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {Data} data
     * @param {Object} ganttData
     */
    _processGanttData(metaData, data, ganttData) {}

    /**
     * @protected
     * @param {MetaData} _metaData
     * @param {Object} _context
     * @returns {Promise<any>}
     */
    async _fetchCompanionData(_metaData, _context) {}

    /**
     * @protected
     * @param {MetaData} _metaData
     * @param {Data} _data
     * @param {any} _companion
     */
    _applyCompanionData(_metaData, _data, _companion) {}

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {string[]} groupedBy
     * @returns {string[]}
     */
    _filterDateIngroupedBy(metaData, groupedBy) {
        return groupedBy.filter((gb) => {
            const [fieldName] = gb.split(":");
            const { type } = metaData.fields[fieldName];
            return !["date", "datetime"].includes(type);
        });
    }

    /**
     * @protected
     * @param {number} floatVal
     * @returns {string}
     */
    _formatTime(floatVal) {
        const timeStr = formatFloatTime(floatVal, { noLeadingZeroHour: true });
        const [hourStr, minuteStr] = timeStr.split(":");
        const hour = parseInt(hourStr, 10);
        const minute = parseInt(minuteStr, 10);
        return minute ? _t("%(hour)sh%(minute)s", { hour, minute }) : _t("%sh", hour);
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {Object} params
     * @param {Object[]} params.groups
     * @param {string[]} params.groupedBy
     * @param {Object[]} params.parentGroup
     * @returns {Row[]}
     */
    _generateRows(metaData, params) {
        const groupedBy = params.groupedBy;
        const groups = params.groups;
        const groupLevel = metaData.groupedBy.length - groupedBy.length;
        const parentGroup = params.parentGroup;

        if (!groupedBy.length || !groups.length) {
            const recordIds = [];
            for (const g of groups) {
                recordIds.push(...(g.__record_ids || []));
            }
            const part = parentGroup.at(-1);
            const [[parentGroupedField, value]] = part ? Object.entries(part) : [[]];
            return [
                {
                    groupLevel,
                    id: JSON.stringify([...parentGroup, {}]),
                    name: "",
                    recordIds: unique(recordIds),
                    parentGroupedField,
                    parentResId: Array.isArray(value) ? value[0] : value,
                    __extra__: true,
                },
            ];
        }

        /** @type {Row[]} */
        const rows = [];

        const groupedByField = groupedBy[0];
        const currentLevelGroups = new Map();
        for (const g of groups) {
            if (g[groupedByField] === undefined) {
                g[groupedByField] = false;
            }
            const key = String(g[groupedByField]);
            if (!currentLevelGroups.has(key)) {
                currentLevelGroups.set(key, []);
            }
            currentLevelGroups.get(key).push(g);
        }
        const { maxField } = metaData.consolidationParams;
        const consolidate = groupLevel === 0 && groupedByField === maxField;
        const generateSubRow = maxField ? true : groupedBy.length > 1;
        for (const subGroups of currentLevelGroups.values()) {
            const value = subGroups[0][groupedByField];
            const part = {};
            part[groupedByField] = value;
            const fakeGroup = [...parentGroup, part];
            const id = JSON.stringify(fakeGroup);
            const resId = Array.isArray(value) ? value[0] : value;
            const fromServer = subGroups.some((g) => g.fromServer);
            const recordIds = [];
            for (const g of subGroups) {
                recordIds.push(...(g.__record_ids || []));
            }
            const row = {
                consolidate,
                fromServer,
                groupedBy,
                groupedByField,
                groupLevel,
                id,
                name: this._getRowName(metaData, groupedByField, value),
                resId,
                recordIds: unique(recordIds),
            };
            if (generateSubRow) {
                row.rows = this._generateRows(metaData, {
                    ...params,
                    groupedBy: groupedBy.slice(1),
                    groups: subGroups,
                    parentGroup: fakeGroup,
                });
            }
            if (resId === false) {
                rows.unshift(row);
            } else {
                rows.push(row);
            }
        }

        return rows;
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @returns {any[]}
     */
    _getDomain(metaData) {
        const { dateStartField, dateStopField, globalStart, globalStop } = metaData;
        const startField = metaData.fields[dateStartField];
        const stopField = metaData.fields[dateStopField];
        const domain = Domain.and([
            this.searchParams.domain,
            [
                "&",
                [dateStartField, "<", serializeDateForField(startField, globalStop)],
                [
                    dateStopField,
                    stopField.type === "date" ? ">=" : ">",
                    serializeDateForField(stopField, globalStart),
                ],
            ],
        ]);
        return domain.toList();
    }

    /**
     * @protected
     * @param {any} value
     * @param {Object} field
     * @returns {string}
     */
    _getFieldFormattedValue(value, field) {
        if (field.type === "boolean") {
            return value ? _t("True") : _t("False");
        } else if (!value) {
            return field.falsy_value_label || _t("Undefined %s", field.string);
        } else if (field.type === "many2many") {
            return value[1];
        }
        const formatter = registry.category("formatters").get(field.type);
        return formatter(value, field);
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @returns {string[]}
     */
    _getFields(metaData) {
        const fields = new Set([
            "display_name",
            metaData.dateStartField,
            metaData.dateStopField,
            ...metaData.groupedBy,
            ...metaData.decorationFields,
        ]);
        if (metaData.colorField) {
            fields.add(metaData.colorField);
        }
        if (metaData.consolidationParams.field) {
            fields.add(metaData.consolidationParams.field);
        }
        if (metaData.consolidationParams.excludeField) {
            fields.add(metaData.consolidationParams.excludeField);
        }
        if (metaData.dependencyField) {
            fields.add(metaData.dependencyField);
        }
        if (metaData.durationField) {
            fields.add(metaData.durationField);
        }
        if (metaData.progressField) {
            fields.add(metaData.progressField);
        }
        return [...fields];
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {{ groupBy: string[] }} searchParams
     * @returns {string[]}
     */
    _getGroupedBy(metaData, searchParams) {
        let groupedBy = [...searchParams.groupBy];
        groupedBy = groupedBy.filter((gb) => {
            const [fieldName] = gb.split(".");
            const field = metaData.fields[fieldName];
            return field?.type !== "properties";
        });
        return this._filterDateIngroupedBy(metaData, groupedBy);
    }

    _getDefaultFocusDate(searchParams) {
        const { context } = searchParams;
        const focusDate =
            "initialDate" in context ? deserializeDateTime(context.initialDate) : now();
        return focusDate.startOfDay();
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {{ context: Record<string, any> }} searchParams
     * @returns {{ focusDate: DateTime, rangeId: ScaleId, startDate: DateTime, stopDate: DateTime }}
     */
    _getInitialRangeParams(metaData, searchParams) {
        const { context } = searchParams;
        const localRangeId = this._getRangeIdFromLocalStorage(metaData);

        const rangeFromContext = context.default_range || context.default_scale;
        const rangeId =
            localRangeId ||
            (Object.hasOwn(metaData.ranges, rangeFromContext)
                ? rangeFromContext
                : metaData.defaultRange);

        if (Object.hasOwn(metaData.ranges, rangeId)) {
            return {
                ...this.rangeAround(rangeId, this._getDefaultFocusDate(searchParams)),
            };
        }
        return {
            rangeId: "custom",
            ...customRangeAround({
                startDate:
                    context.default_start_date &&
                    toDateTime(deserializeDate(context.default_start_date)),
                stopDate:
                    context.default_stop_date &&
                    toDateTime(deserializeDate(context.default_stop_date)),
                focusDate: this._getDefaultFocusDate(searchParams),
                today: now(),
            }),
        };
    }

    _getLocalStorageKey() {
        return `rangeOf-${this.metaData.resModel}-viewId-${this.viewContext.config.viewId}`;
    }

    _getProgressBarFields(metaData) {
        if (metaData.progressBarFields && !this.orm.isSample) {
            return metaData.progressBarFields.filter(
                (fieldName) =>
                    metaData.groupedBy.includes(fieldName) &&
                    ["many2many", "many2one"].includes(
                        metaData.fields[fieldName]?.type,
                    ),
            );
        }
        return [];
    }

    _getRescheduleContext() {
        return { ...this.searchParams.context };
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {string} groupedByField
     * @param {any} value
     * @returns {string}
     */
    _getRowName(metaData, groupedByField, value) {
        const field = metaData.fields[groupedByField];
        return this._getFieldFormattedValue(value, field);
    }

    _getRangeIdFromLocalStorage(metaData) {
        return this._getStoredChoice(this._getLocalStorageKey(), metaData.ranges);
    }

    _getStoredChoice(key, allowed) {
        const stored = browser.localStorage.getItem(key);
        return Object.hasOwn(allowed, stored) ? stored : null;
    }

    _getInitialRescheduleMethod(metaData) {
        return {
            rescheduleMethod:
                this._getRescheduleMethodFromLocalStorage(metaData) ||
                metaData.defaultRescheduleMethod,
        };
    }

    _getRescheduleMethodLocalStorageKey() {
        return `rescheduleMethod-${this.metaData.resModel}-viewId-${this.viewContext.config.viewId}`;
    }

    _getRescheduleMethodFromLocalStorage(metaData) {
        return this._getStoredChoice(
            this._getRescheduleMethodLocalStorageKey(),
            metaData.rescheduleMethods,
        );
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @returns {string[]}
     */
    _getUnavailabilityFields(metaData) {
        if (
            metaData.displayUnavailability &&
            !this.orm.isSample &&
            metaData.groupedBy.length
        ) {
            const lastGroupBy = metaData.groupedBy.at(-1);
            const { type } = metaData.fields[lastGroupBy] || {};
            if (["many2many", "many2one"].includes(type)) {
                return [lastGroupBy];
            }
        }
        return [];
    }

    /**
     * @protected
     * @param {MetaData} metaData
     * @param {Record<string, any>[]} records
     * @returns {Record<string, any>[]}
     */
    _parseServerData(metaData, records) {
        const { dateStartField, dateStopField, fields } = metaData;
        /** @type {Record<string, any>[]} */
        const parsedRecords = [];
        for (const record of records) {
            const parsedRecord = parseServerValues(fields, record);
            const dateStart = parsedRecord[dateStartField];
            const dateStop = parsedRecord[dateStopField];
            if (
                dateStart &&
                dateStop &&
                compareDates(toDateTime(dateStart), toDateTime(dateStop)) <= 0
            ) {
                parsedRecords.push(parsedRecord);
            }
        }
        return parsedRecords;
    }

    _processProgressBar(progressBar, warning) {
        const processedProgressBar = {
            ...progressBar,
            value_formatted: this._formatTime(progressBar.value),
            max_value_formatted: this._formatTime(progressBar.max_value),
            ratio: progressBar.max_value
                ? (progressBar.value / progressBar.max_value) * 100
                : 0,
            warning,
        };
        if (processedProgressBar.max_value) {
            processedProgressBar.ratio_formatted = formatPercentage(
                processedProgressBar.ratio / 100,
            );
        }
        return processedProgressBar;
    }

    _processProgressBars(progressBars) {
        return mapByFieldAndResId(progressBars, (progressBar, warning) =>
            this._processProgressBar(progressBar, warning),
        );
    }

    _processUnavailabilities(unavailabilities) {
        return mapByFieldAndResId(unavailabilities, (resUnavailabilities) =>
            resUnavailabilities.map((u) => ({
                start: deserializeDateTime(u.start),
                stop: deserializeDateTime(u.stop),
            })),
        );
    }

    /**
     * @template {Record<string, any>} T
     * @param {T} schedule
     * @returns {Partial<T>}
     */
    _scheduleToData(schedule) {
        const allowedFields = [
            this.metaData.dateStartField,
            this.metaData.dateStopField,
            ...this.metaData.groupedBy,
        ];
        return pick(schedule, ...allowedFields);
    }
}
