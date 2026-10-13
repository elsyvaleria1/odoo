/** @odoo-module native */
import { markRaw, toRaw } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { Domain } from "@web/core/domain";
import {
    compareDates,
    dateSettings,
    deserializeDate,
    endOf,
    serializeDate,
    startOf,
    today,
    withWeekday,
} from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { pyToJsLocale } from "@web/core/l10n/utils";
import { _t } from "@web/core/translation";
import { KeepLast, Mutex } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { Model } from "@web/model/model";

/**
 * @param {Temporal.PlainDate} date
 * @param {string} granularity
 * @param {number} count
 */
export function addGranularity(date, granularity, count) {
    const unit = dateUnit(granularity);
    return unit === "quarter"
        ? date.add({ months: 3 * count })
        : date.add({ [`${unit}s`]: count });
}

/**
 * @param {string} unit
 * @returns {any}
 */
function dateUnit(unit) {
    const lower = unit.toLowerCase();
    return lower.endsWith("s") ? lower.slice(0, -1) : lower;
}

export class GridCell {
    /**
     * @param model
     * @param row
     * @param column
     * @param value
     */
    constructor(model, row, column, value = 0) {
        this.row = row;
        this.column = column;
        this.model = model;
        this.value = value;
        this._readonly = false;
    }

    get readonly() {
        return this._readonly || this.column.readonly;
    }

    /** @return {Domain} */
    get domain() {
        const domains = [
            this.model.searchParams.domain,
            this.row.domain,
            this.column.domain,
        ];
        return Domain.and(domains);
    }

    get context() {
        return {
            ...this.model.searchParams.context,
            ...this.row.section?.context,
            ...this.row.context,
            ...this.column.context,
        };
    }

    get title() {
        const rowTitle =
            !this.row.section || this.row.section.isFake
                ? this.row.title
                : `${this.row.section.title} / ${this.row.title}`;
        const columnTitle = this.column.title;
        return `${rowTitle} (${columnTitle})`;
    }

    /** @param {Number} value */
    async update(value) {
        return this.model.mutex.exec(async () => {
            await this._update(value);
        });
    }

    async _update(value) {
        const oldValue = this.value;
        const data = this.model.data;
        const result = await this.model.orm.call(
            this.model.resModel,
            "grid_update_cell",
            [this.domain.toList({}), this.model.measureFieldName, value - oldValue],
            { context: this.context },
        );
        if (result) {
            await this.model.actionService.doAction(result);
            return;
        }
        if (this.model.data !== data) {
            await this.model.reload();
            return;
        }
        this.row.updateCell(this.column, value);
        this.model.notify();
    }
}

export class GridRow {
    /**
     * @param data
     * @param domain
     * @param valuePerFieldName
     * @param model
     * @param section
     * @param isAdditionalRow
     */
    constructor(
        data,
        domain,
        valuePerFieldName,
        model,
        section,
        isAdditionalRow = false,
    ) {
        this._domain = domain;
        this.model = model;
        this.data = data;
        this.cells = {};
        this.valuePerFieldName = valuePerFieldName;
        this.id = data.nextRowId++;
        this.section = section;
        this.section?.addRow(this);
        this.grandTotal = 0;
        this.grandTotalWeekendHidden = 0;
        this.isAdditionalRow = isAdditionalRow;
        this._generateCells(data);
    }

    get initialRecordValues() {
        return this.valuePerFieldName;
    }

    get title() {
        const labelArray = [];
        for (const rowField of this.data.rowFields) {
            let title = this.valuePerFieldName[rowField.name];
            if (this.model.isPairValued(rowField)) {
                title = title ? title[1] : !labelArray.length && _t("None");
            }
            if (title) {
                labelArray.push(title);
            }
        }
        return labelArray.join(" / ");
    }

    get domain() {
        if (this.section.isFake) {
            return this._domain;
        }
        return Domain.and([this.section.domain, this._domain]);
    }

    get context() {
        const context = {};
        const rowFieldPerName = Object.fromEntries(
            this.data.rowFields.map((r) => [r.name, r]),
        );
        for (const [name, value] of Object.entries(this.valuePerFieldName)) {
            context[`default_${name}`] = this.model.getGroupValue(
                rowFieldPerName[name] || { name },
                value,
            );
        }
        return context;
    }

    getSection() {
        return !this.section.isFake && this.section;
    }

    /** @private */
    _generateCells(data) {
        for (const column of Object.values(data.columns)) {
            this.cells[column.id] = new this.model.constructor.Cell(
                this.model,
                this,
                column,
                0,
            );
        }
    }

    _ensureColumnExist(column) {
        if (!(column.id in this.cells)) {
            throw new Error("Unbound index: the columnId is not in the row columns");
        }
    }

    /**
     * @param {GridColumn} column
     * @param {number} value
     */
    updateCell(column, value) {
        this._ensureColumnExist(column);
        const cell = this.cells[column.id];
        const oldValue = cell.value;
        cell.value = value;
        const delta = value - oldValue;
        this.section.updateGrandTotal(column, delta);
        this.grandTotal += delta;
        this.grandTotalWeekendHidden += column.isWeekDay ? delta : 0;
        column.grandTotal += delta;
        if (this.isAdditionalRow && delta !== 0) {
            this.isAdditionalRow = false;
        }
    }

    setReadonlyCell(column, readonly) {
        this._ensureColumnExist(column);
        this.cells[column.id]._readonly = Array.isArray(readonly)
            ? readonly.length > 0
            : Boolean(readonly);
    }

    getGrandTotal(showWeekend) {
        return showWeekend ? this.grandTotal : this.grandTotalWeekendHidden;
    }
}

export class GridSection extends GridRow {
    constructor() {
        super(...arguments);
        this.rows = {};
        this.isSection = true;
        this.lastRow = null;
    }

    get sectionField() {
        return this.data.sectionField;
    }

    get value() {
        const { sectionField } = this;
        return sectionField && this.valuePerFieldName
            ? this.valuePerFieldName[sectionField.name]
            : null;
    }

    get domain() {
        return this.model._getGroupDomain(this.sectionField, this.value);
    }

    get title() {
        if (this.sectionField && this.model.isPairValued(this.sectionField)) {
            return (this.value && this.value[1]) || _t("None");
        }
        return this.value;
    }

    get initialRecordValues() {
        return this.sectionField ? { [this.sectionField.name]: this.value } : {};
    }

    get isFake() {
        return this.value == null;
    }

    get context() {
        if (this.isFake) {
            return {};
        }
        const { sectionField } = this;
        return {
            [`default_${sectionField.name}`]: this.model.getGroupValue(
                sectionField,
                this.value,
            ),
        };
    }

    getSection() {
        return !this.isFake && this;
    }

    /** @param row */
    addRow(row) {
        if (row.id in this.rows) {
            throw new Error("Row already added in section");
        }
        this.rows[row.id] = row;
        this.lastRow = row;
    }

    /**
     * @param column
     * @param delta
     */
    updateGrandTotal(column, delta) {
        this.cells[column.id].value += delta;
        this.grandTotal += delta;
        this.grandTotalWeekendHidden += column.isWeekDay ? delta : 0;
    }
}

export class GridColumn {
    /**
     * @param data
     * @param model
     * @param title
     */
    constructor(data, model, title, value, readonly = false) {
        this.model = model;
        this.title = title;
        this.value = value;
        this.id = data.nextColumnId++;
        this.grandTotal = 0;
        this.readonly = readonly;
    }

    get domain() {
        return new Domain([[this.model.columnFieldName, "=", this.value]]);
    }

    get context() {
        return { [`default_${this.model.columnFieldName}`]: this.value };
    }
}

export class DateGridColumn extends GridColumn {
    /**
     * @param data
     * @param model
     * @param title
     * @param dateStart
     * @param dateEnd
     * @param isToday
     * @param isWeekDay
     */
    constructor(
        data,
        model,
        title,
        dateStart,
        dateEnd,
        isToday,
        isWeekDay,
        readonly = false,
    ) {
        super(data, model, title, dateStart, readonly);
        this.dateEnd = dateEnd;
        this.isToday = isToday;
        this.isWeekDay = isWeekDay;
    }

    get domain() {
        return new Domain([
            "&",
            [this.model.columnFieldName, ">=", this.value],
            [this.model.columnFieldName, "<", this.dateEnd],
        ]);
    }
}

export class GridNavigationInfo {
    constructor(anchor, model) {
        this.anchor = anchor;
        this.model = model;
    }

    get _targetWeekday() {
        const firstDayOfWeek = localization.weekStart;
        return this.anchor.dayOfWeek < firstDayOfWeek
            ? firstDayOfWeek - 7
            : firstDayOfWeek;
    }

    get periodStart() {
        if (this.range.span !== "week") {
            return startOf(this.anchor, dateUnit(this.range.span));
        }
        return withWeekday(this.anchor, this._targetWeekday);
    }

    get periodEnd() {
        if (this.range.span !== "week") {
            return endOf(this.anchor, dateUnit(this.range.span));
        }
        return withWeekday(this.anchor, this._targetWeekday).add({ days: 6 });
    }

    /**
     * @param {Temporal.PlainDate} day
     */
    contains(day) {
        return (
            compareDates(this.periodStart, day) <= 0 &&
            compareDates(day, this.periodEnd) <= 0
        );
    }

    async prepare() {}
}

export class GridModel extends Model {
    static Cell = GridCell;
    static Column = GridColumn;
    static DateColumn = DateGridColumn;
    static Row = GridRow;
    static Section = GridSection;
    static NavigationInfo = GridNavigationInfo;

    get data() {
        void this.updateEpoch;
        return this._data;
    }

    set data(data) {
        toRaw(this)._data = data && markRaw(data);
    }

    setup(params) {
        this.notificationService = useService("notification");
        this.actionService = useService("action");
        this.keepLast = new KeepLast();
        this.mutex = new Mutex();
        this.defaultSectionField = params.sectionField;
        this.defaultRowFields = params.rowFields;
        this.sectionField = undefined;
        this.rowFields = [];
        this.searchParams = {};
        this.resModel = params.resModel;
        this.fieldsInfo = params.fieldsInfo;
        this.columnFieldName = params.columnFieldName;
        this.columnFieldIsDate =
            this.fieldsInfo[params.columnFieldName].type === "date";
        this.measureField = params.measureField;
        this.readonlyField = params.readonlyField;
        this.ranges = params.ranges;
        this.withRecordIds = params.withRecordIds ?? true;
        this.defaultAnchor = params.defaultAnchor || this.today;
        this.navigationInfo = new this.constructor.NavigationInfo(
            this.defaultAnchor,
            this,
        );
        this.data = undefined;
        this.record = undefined;
        const range = this._getInitialRange(params);
        if (range) {
            this.navigationInfo.range = range;
        } else if (this.columnFieldIsDate) {
            throw new Error(
                "A grid view whose column field is a date must declare at least one <range> element.",
            );
        }
    }

    /**
     * @private
     * @return {Object|undefined}
     */
    _getInitialRange(params) {
        const storedRangeName = browser.localStorage.getItem(this.storageKey);
        return this.ranges[storedRangeName] || this.ranges[params.activeRangeName];
    }

    get aggregates() {
        const aggregates = [this.measureGroupByFieldName];
        if (this.withRecordIds) {
            aggregates.push("id:array_agg");
        }
        if (this.readonlyField) {
            aggregates.push(this.readonlyGroupByFieldName);
        }
        return aggregates;
    }

    get today() {
        return today();
    }

    get sectionsArray() {
        return Object.values(this.data.sections);
    }

    get rowsArray() {
        return Object.values(this.data.rows);
    }

    get columnsArray() {
        return Object.values(this.data.columns);
    }

    get itemsArray() {
        return this.data.items;
    }

    get maxColumnsTotal() {
        return Math.max(0, ...this.columnsArray.map((c) => c.grandTotal));
    }

    get measureFieldName() {
        return this.measureField.name;
    }

    get measureGroupByFieldName() {
        return `${this.measureFieldName}:${this.measureField.aggregator}`;
    }

    /** @return {string|undefined} */
    get readonlyGroupByFieldName() {
        return (
            this.readonlyField &&
            `${this.readonlyField.name}:${this.readonlyField.aggregator}`
        );
    }

    get storageKey() {
        return `scaleOf-viewId-${this.viewContext.config.viewId}`;
    }

    get columnGroupByFieldName() {
        let columnGroupByFieldName = this.columnFieldName;
        if (this.columnFieldIsDate) {
            columnGroupByFieldName += `:${this.navigationInfo.range.step}`;
        }
        return columnGroupByFieldName;
    }

    /**
     * @param {Temporal.PlainDate} date
     */
    isToday(date) {
        return date.equals(this.today);
    }

    /**
     * @private
     * @param {Object} metaData
     * @return {string[]}
     */
    _getGroupByFields({ rowFields, sectionField }) {
        const fields = [
            this.columnGroupByFieldName,
            ...rowFields.map((r) => this.getGroupBySpec(r)),
        ];
        if (sectionField) {
            fields.push(this.getGroupBySpec(sectionField));
        }
        return fields;
    }

    /**
     * @private
     * @param {string} groupBy
     * @return {{name: string, granularity: string|undefined}}
     */
    _parseGroupBy(groupBy) {
        const [name, granularity] = groupBy.split(":");
        return { name, granularity };
    }

    /**
     * @param {{name: string, granularity?: string}} field
     * @return {string}
     */
    getGroupBySpec(field) {
        return field.granularity ? `${field.name}:${field.granularity}` : field.name;
    }

    /**
     * @param {{name: string, granularity?: string}} field
     * @return {boolean}
     */
    isPairValued(field) {
        return Boolean(
            field.granularity || this.fieldsInfo[field.name].type === "many2one",
        );
    }

    /**
     * @param {{name: string, granularity?: string}} field
     * @param {*} rawValue
     * @return {*}
     */
    getGroupValue(field, rawValue) {
        return this.isPairValued(field) ? rawValue && rawValue[0] : rawValue;
    }

    /**
     * @private
     * @param {{name: string, granularity?: string}} field
     * @param {*} rawValue
     * @return {Domain}
     */
    _getGroupDomain(field, rawValue) {
        const value = this.getGroupValue(field, rawValue);
        if (field.granularity && value) {
            const periodEnd = addGranularity(
                deserializeDate(value),
                field.granularity,
                1,
            );
            return new Domain([
                "&",
                [field.name, ">=", value],
                [field.name, "<", serializeDate(periodEnd)],
            ]);
        }
        return new Domain([[field.name, "=", value]]);
    }

    _getDateColumnTitle(date) {
        const granularity = this.navigationInfo.range.step;
        if (!["day", "month"].includes(granularity)) {
            return serializeDate(date);
        }
        const locale = pyToJsLocale(dateSettings.locale) || undefined;

        const options = {
            day: { weekday: "short", month: "short", day: "numeric" },
            month: { month: "long", year: "numeric" },
        }[granularity];

        const parts = new Intl.DateTimeFormat(locale, {
            ...options,
            timeZone: "UTC",
        }).formatToParts(new Date(date.toZonedDateTime("UTC").epochMilliseconds));

        const splitAfter = granularity === "day" ? "weekday" : "month";

        let splitIndex = parts.findIndex((p) => p.type === splitAfter);
        if (splitIndex === -1) {
            return parts.map((p) => p.value).join("");
        }

        while (++splitIndex < parts.length) {
            if (parts[splitIndex].type === "literal") {
                break;
            }
        }

        const firstLineParts = parts.slice(0, splitIndex + 1);
        const secondLineParts = parts.slice(splitIndex + 1);

        const firstLine = firstLineParts
            .map((p) => p.value)
            .join("")
            .trim();
        const secondLine = secondLineParts
            .map((p) => p.value)
            .join("")
            .trim();
        return `${firstLine}\n${secondLine}`;
    }

    /**
     * @override
     */
    hasData() {
        return this.sectionsArray.length > 0;
    }

    /** @param rangeName */
    async setRange(rangeName) {
        this.navigationInfo.range = this.ranges[rangeName];
        browser.localStorage.setItem(this.storageKey, rangeName);
        await this.reload();
    }

    async setAnchor(anchor) {
        this.navigationInfo.anchor = anchor;
        await this.reload();
    }

    async setTodayAnchor() {
        await this.setAnchor(this.today);
    }

    generateNavigationDomain() {
        if (this.columnFieldIsDate) {
            const { periodStart, periodEnd } = this.navigationInfo;
            return new Domain([
                "&",
                [this.columnFieldName, ">=", serializeDate(periodStart)],
                [this.columnFieldName, "<=", serializeDate(periodEnd)],
            ]);
        } else {
            return Domain.TRUE;
        }
    }

    async resetAnchor() {
        await this.setAnchor(this.defaultAnchor);
    }

    /** @param direction */
    async moveAnchor(direction) {
        if (direction === "forward") {
            this.navigationInfo.anchor = addGranularity(
                this.navigationInfo.anchor,
                this.navigationInfo.range.span,
                1,
            );
        } else if (direction === "backward") {
            this.navigationInfo.anchor = addGranularity(
                this.navigationInfo.anchor,
                this.navigationInfo.range.span,
                -1,
            );
        } else {
            throw Error("Invalid argument");
        }
        await this.navigationInfo.prepare();
        if (this.navigationInfo.contains(this.today)) {
            this.navigationInfo.anchor = this.today;
        }
        await this.reload();
    }

    async loadData(metaData) {
        await this.navigationInfo.prepare();
        const [initialData, dataFetched, additionalDataFetched] = await Promise.all([
            this._getInitialData(metaData),
            this.fetchData(metaData),
            Promise.all(this._fetchAdditionalData(metaData)),
        ]);
        Object.assign(metaData, initialData);
        const { data, sectionField } = metaData;

        const mergeAdditionalData = (fetchedData) => {
            const additionalData = {};
            for (const fetchedDatum of fetchedData) {
                for (const [sectionKey, sectionInfo] of Object.entries(fetchedDatum)) {
                    if (!(sectionKey in additionalData)) {
                        additionalData[sectionKey] = sectionInfo;
                    } else {
                        for (const [rowKey, rowInfo] of Object.entries(
                            sectionInfo.rows,
                        )) {
                            if (!(rowKey in additionalData[sectionKey].rows)) {
                                additionalData[sectionKey].rows[rowKey] = rowInfo;
                            }
                        }
                    }
                }
            }
            return additionalData;
        };

        const appendAdditionData = (additionalData) => {
            for (const [sectionKey, sectionInfo] of Object.entries(additionalData)) {
                if (!(sectionKey in data.sectionsKeyToIdMapping)) {
                    if (sectionField) {
                        const newSection = new this.constructor.Section(
                            data,
                            null,
                            { [sectionField.name]: sectionInfo.value },
                            this,
                            null,
                        );
                        data.sections[newSection.id] = newSection;
                        data.sectionsKeyToIdMapping[sectionKey] = newSection.id;
                        data.rows[newSection.id] = newSection;
                        data.rowsKeyToIdMapping[sectionKey] = newSection.id;
                    } else {
                        this._getFakeSection(data);
                    }
                }
                const section = data.sections[data.sectionsKeyToIdMapping[sectionKey]];
                for (const [rowKey, rowInfo] of Object.entries(sectionInfo.rows)) {
                    if (!(rowKey in data.rowsKeyToIdMapping)) {
                        const newRow = new this.constructor.Row(
                            data,
                            rowInfo.domain,
                            rowInfo.values,
                            this,
                            section,
                            true,
                        );
                        data.rows[newRow.id] = newRow;
                        data.rowsKeyToIdMapping[rowKey] = newRow.id;
                    }
                }
            }
        };

        await this._generateData(dataFetched, metaData);
        appendAdditionData(mergeAdditionalData(additionalDataFetched));
        if (!this.orm.isSample) {
            const [, postFetchAdditionalData] = await Promise.all([
                Promise.all(this._getAdditionalPromises(metaData)),
                Promise.all(this._postFetchAdditionalData(metaData)),
            ]);
            appendAdditionData(mergeAdditionalData(postFetchAdditionalData));
        }

        const { items } = data;
        for (const section of Object.values(data.sections)) {
            items.push(section);
            this._itemsPostProcess(section, metaData);
            for (const rowId in section.rows) {
                const row = section.rows[rowId];
                this._itemsPostProcess(row, metaData);
                items.push(row);
            }
        }
    }

    /**
     * @override
     * @param params
     * @return {Promise<void>}
     */
    async load(params = {}) {
        const searchParams = {
            ...this.searchParams,
            ...params,
        };
        const groupBys = [];
        let notificationDisplayed = false;
        for (const groupBy of searchParams.groupBy) {
            if (this._isColumnFieldGroupBy(groupBy)) {
                if (!notificationDisplayed) {
                    this.notificationService.add(
                        _t(
                            "Grouping by the field used in the column of the grid view is not possible.",
                        ),
                        { type: "warning" },
                    );
                    notificationDisplayed = true;
                }
            } else {
                groupBys.push(groupBy);
            }
        }
        if (searchParams.groupBy.length !== groupBys.length) {
            searchParams.groupBy = groupBys;
        }
        let rowFields = [];
        let sectionField;
        if (searchParams.groupBy.length) {
            if (
                this.defaultSectionField &&
                searchParams.groupBy.length > 1 &&
                searchParams.groupBy[0] === this.defaultSectionField.name
            ) {
                sectionField = this.defaultSectionField;
            }
            const rowFieldPerFieldName = Object.fromEntries(
                this.defaultRowFields.map((r) => [r.name, r]),
            );
            for (const groupBy of searchParams.groupBy) {
                if (sectionField && groupBy === sectionField.name) {
                    continue;
                }
                const { name, granularity } = this._parseGroupBy(groupBy);
                rowFields.push({
                    ...rowFieldPerFieldName[name],
                    name,
                    granularity,
                    invisible: false,
                });
            }
        } else {
            if (this.defaultSectionField && !this.defaultSectionField.invisible) {
                sectionField = this.defaultSectionField;
            }
            rowFields = this.defaultRowFields.filter((r) => !r.invisible);
        }

        const metaData = {
            searchParams,
            rowFields,
            sectionField,
        };
        await this.keepLast.add(this.loadData(metaData));
        Object.assign(this, {
            ...metaData,
        });
    }

    /**
     * @private
     * @param {string} groupBy
     * @return {boolean}
     */
    _isColumnFieldGroupBy(groupBy) {
        return groupBy.split(":", 1)[0] === this.columnFieldName;
    }

    async reload(params = {}) {
        await this.load(params);
        this.useSampleModel = false;
        this.notify();
    }

    /** @private */
    _generateDateColumns({ data }) {
        const { step } = this.navigationInfo.range;
        const generateNext = (dateStart) => addGranularity(dateStart, step, 1);
        for (
            let currentDate = this.navigationInfo.periodStart;
            compareDates(currentDate, this.navigationInfo.periodEnd) <= 0;
            currentDate = generateNext(currentDate)
        ) {
            const domainStart = currentDate;
            const domainStop = generateNext(currentDate);
            const domainStartSerialized = serializeDate(domainStart);
            const isWeekDay = step !== "day" || currentDate.dayOfWeek < 6;
            const column = new this.constructor.DateColumn(
                data,
                this,
                this._getDateColumnTitle(currentDate),
                domainStartSerialized,
                serializeDate(domainStop),
                this.isToday(currentDate),
                isWeekDay,
            );
            data.columns[column.id] = column;
            data.columnsKeyToIdMapping[domainStartSerialized] = column.id;
        }
    }

    /**
     * @param {Array} [domain]
     * @param {string} [readonlyField]
     * @returns {Array}
     */
    /**
     * @private
     * @return {Object}
     */
    get _columnsOrm() {
        return this.orm.isSample ? Object.getPrototypeOf(this.orm) : this.orm;
    }

    async _searchMany2oneColumns(domain, readonlyField) {
        const fieldsToFetch = ["id", "display_name"];
        if (readonlyField) {
            fieldsToFetch.push(readonlyField);
        }
        const columnField = this.fieldsInfo[this.columnFieldName];
        const columnRecords = await this._columnsOrm.searchRead(
            columnField.relation,
            domain || [],
            fieldsToFetch,
        );
        return columnRecords.map((record) => fieldsToFetch.map((f) => record[f]));
    }

    /** @private */
    async _getInitialData({ sectionField, rowFields }) {
        const initialData = {
            data: {
                sectionField,
                rowFields,
                nextRowId: 0,
                nextColumnId: 0,
                columnsKeyToIdMapping: {},
                columns: {},
                rows: {},
                rowsKeyToIdMapping: {},
                fieldsInfo: this.fieldsInfo,
                sections: {},
                sectionsKeyToIdMapping: {},
                items: [],
            },
            record: {
                context: {},
                resModel: this.resModel,
                resIds: [],
            },
        };
        let columnRecords;
        const columnField = this.fieldsInfo[this.columnFieldName];
        if (this.columnFieldIsDate) {
            this._generateDateColumns(initialData);
        } else {
            if (columnField.type === "selection") {
                const selectionFieldValues = await this._columnsOrm.call(
                    "ir.model.fields",
                    "get_field_selection",
                    [this.resModel, this.columnFieldName],
                );
                columnRecords = selectionFieldValues;
            } else if (columnField.type === "many2one") {
                columnRecords = await this._searchMany2oneColumns();
            } else {
                throw new Error(
                    "Unmanaged column type. Supported types are date, selection and many2one.",
                );
            }
            for (const record of columnRecords) {
                let readonly = false;
                let key, value;
                if (record.length === 2) {
                    [key, value] = record;
                } else {
                    [key, value, readonly] = record;
                }
                const column = new this.constructor.Column(
                    initialData.data,
                    this,
                    value,
                    key,
                    Boolean(readonly),
                );
                initialData.data.columns[column.id] = column;
                initialData.data.columnsKeyToIdMapping[key] = column.id;
            }
        }
        return initialData;
    }

    async fetchData(metaData) {
        const { searchParams } = metaData;
        let dataFetched = await this.orm.formattedReadGroup(
            this.resModel,
            Domain.and([searchParams.domain, this.generateNavigationDomain()]).toList(
                {},
            ),
            this._getGroupByFields(metaData),
            this.aggregates,
        );
        if (this.orm.isSample && this.columnFieldIsDate) {
            dataFetched = dataFetched.filter((group) => {
                const date = deserializeDate(group[this.columnGroupByFieldName][0]);
                const { periodStart, periodEnd } = this.navigationInfo;
                return (
                    compareDates(date, periodStart) >= 0 &&
                    compareDates(date, periodEnd) <= 0
                );
            });
        }
        return dataFetched;
    }

    /**
     * @return {Array<Promise<Object>>}
     * @private
     */
    _fetchAdditionalData(metaData) {
        return [];
    }

    /**
     * @return {Array<Promise<Object>>}
     * @private
     */
    _postFetchAdditionalData(metaData) {
        return [];
    }

    _getAdditionalPromises(metaData) {
        return this.usesUnavailability ? [this._fetchUnavailabilityDays(metaData)] : [];
    }

    /** @return {boolean} */
    get usesUnavailability() {
        return false;
    }

    async _fetchUnavailabilityDays(metaData, args = {}) {
        if (!this.columnFieldIsDate) {
            return;
        }
        const result = await this.orm.call(
            this.resModel,
            "grid_unavailability",
            [
                serializeDate(this.navigationInfo.periodStart),
                serializeDate(this.navigationInfo.periodEnd),
            ],
            {
                ...args,
            },
        );
        this._processUnavailabilityDays(result, metaData);
    }

    /**
     * @param {Object} result
     * @param {Object} metaData
     */
    _processUnavailabilityDays(result, metaData) {}

    /**
     * @param readGroupResult
     * @private
     * @return {string}
     */
    _generateRowKey(readGroupResult, { sectionField, rowFields }) {
        const sectionKey = sectionField
            ? this._generateSectionKey(readGroupResult, sectionField)
            : false;
        return this._composeRowKey(
            sectionKey,
            rowFields.map((rowField) =>
                this.getGroupValue(
                    rowField,
                    this._getGroupRawValue(readGroupResult, rowField),
                ),
            ),
        );
    }

    /**
     * @param {Object} values
     * @param {{sectionField?: Object, rowFields: Object[]}} metaData
     * @return {string}
     */
    _generateRowKeyFromValues(values, { sectionField, rowFields }) {
        const sectionKey = sectionField
            ? this._composeSectionKey(values[sectionField.name] ?? false)
            : false;
        return this._composeRowKey(
            sectionKey,
            rowFields.map((rowField) => values[rowField.name] ?? false),
        );
    }

    _composeRowKey(sectionKey, rowValues) {
        return `${sectionKey}@|@${rowValues.map((value) => `${value}\\|/`).join("")}`;
    }

    _composeSectionKey(value) {
        return `/|\\${value}`;
    }

    /**
     * @private
     * @param {Object} readGroupResult
     * @param {{name: string, granularity?: string}} field
     * @return {*}
     */
    _getGroupRawValue(readGroupResult, field) {
        const spec = this.getGroupBySpec(field);
        return spec in readGroupResult && readGroupResult[spec];
    }

    /**
     * @private
     * @param {Object} readGroupResult
     * @return {*}
     */
    _getColumnKey(readGroupResult) {
        const rawValue = readGroupResult[this.columnGroupByFieldName];
        if (this.columnFieldIsDate) {
            return rawValue[0];
        }
        return this.fieldsInfo[this.columnFieldName].type === "many2one"
            ? rawValue && rawValue[0]
            : rawValue;
    }

    /**
     * @param readGroupResult
     * @private
     */
    _generateSectionKey(readGroupResult, sectionField) {
        const rawValue = readGroupResult[this.getGroupBySpec(sectionField)];
        return this._composeSectionKey(this.getGroupValue(sectionField, rawValue));
    }

    /**
     * @param readGroupResult
     * @return {{domain: Domain, values: Object}}
     */
    _generateRowDomainAndValues(readGroupResult, rowFields) {
        let domain = new Domain();
        const values = {};
        for (const rowField of rowFields) {
            const rawValue = this._getGroupRawValue(readGroupResult, rowField);
            values[rowField.name] = rawValue;
            domain = Domain.and([domain, this._getGroupDomain(rowField, rawValue)]);
        }
        return { domain, values };
    }

    /** @private */
    _getFakeSection(data) {
        const sectionId = data.sectionsKeyToIdMapping["false"];
        return sectionId === undefined
            ? this._generateFakeSection(data)
            : data.sections[sectionId];
    }

    _generateFakeSection(data) {
        const section = new this.constructor.Section(data, null, null, this, null);
        data.sections[section.id] = section;
        data.sectionsKeyToIdMapping["false"] = section.id;
        data.rows[section.id] = section;
        data.rowsKeyToIdMapping["false"] = section.id;
        return section;
    }

    async _generateData(readGroupResults, metaData) {
        const { data, record, sectionField, rowFields } = metaData;
        let section;
        for (const readGroupResult of readGroupResults) {
            const columnId =
                data.columnsKeyToIdMapping[this._getColumnKey(readGroupResult)];
            if (!(columnId in data.columns)) {
                continue;
            }
            if (this.withRecordIds && !this.orm.isSample) {
                record.resIds.push(...readGroupResult["id:array_agg"]);
            }
            const rowKey = this._generateRowKey(readGroupResult, metaData);
            if (sectionField) {
                const sectionKey = this._generateSectionKey(
                    readGroupResult,
                    sectionField,
                );
                if (!(sectionKey in data.sectionsKeyToIdMapping)) {
                    const newSection = new this.constructor.Section(
                        data,
                        null,
                        {
                            [sectionField.name]:
                                readGroupResult[this.getGroupBySpec(sectionField)],
                        },
                        this,
                        null,
                    );
                    data.sections[newSection.id] = newSection;
                    data.sectionsKeyToIdMapping[sectionKey] = newSection.id;
                    data.rows[newSection.id] = newSection;
                    data.rowsKeyToIdMapping[sectionKey] = newSection.id;
                }
                section = data.sections[data.sectionsKeyToIdMapping[sectionKey]];
            } else {
                section = this._getFakeSection(data);
            }
            let row;
            if (!(rowKey in data.rowsKeyToIdMapping)) {
                const { domain, values } = this._generateRowDomainAndValues(
                    readGroupResult,
                    rowFields,
                );
                row = new this.constructor.Row(data, domain, values, this, section);
                data.rows[row.id] = row;
                data.rowsKeyToIdMapping[rowKey] = row.id;
            } else {
                row = data.rows[data.rowsKeyToIdMapping[rowKey]];
            }
            const column = data.columns[columnId];
            row.updateCell(column, readGroupResult[this.measureGroupByFieldName]);
            const readonlyAggregate = this.readonlyGroupByFieldName;
            if (readonlyAggregate && readonlyAggregate in readGroupResult) {
                row.setReadonlyCell(column, readGroupResult[readonlyAggregate]);
            }
        }
    }

    /** @param item */
    _itemsPostProcess(item, metaData) {}
}
