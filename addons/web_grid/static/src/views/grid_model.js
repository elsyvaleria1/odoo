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
 * An arch's unit in any case or number ("Year", "months") as the date
 * helpers name it ("year", "month").
 *
 * @param {string} unit
 * @returns {any}
 */
function dateUnit(unit) {
    const lower = unit.toLowerCase();
    return lower.endsWith("s") ? lower.slice(0, -1) : lower;
}

export class GridCell {
    /**
     * Constructor
     *
     * @param model {GridModel} the grid model.
     * @param row {GridRow} the grid row linked to the cell.
     * @param column {GridColumn} the grid column linked to the cell.
     * @param value {Number} the value of the cell.
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

    /**
     * Get the domain of the cell, it will be the domain of row AND the one of the column associated
     *
     * @return {Domain} the domain of the cell
     */
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

    /**
     * Update the grid cell according to the value set by the current user.
     *
     * @param {Number} value the value entered by the current user.
     */
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
     * Constructor
     *
     * @param data {Object} the row data.
     * @param domain {Domain} the domain of the row.
     * @param valuePerFieldName {{string: string}} the field values used to display the row label.
     * @param model {GridModel} the grid model.
     * @param section {GridSection} the section of the grid.
     * @param isAdditionalRow {Boolean} whether the row is an additional (non-data) row.
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

    /**
     * Generate the cells for each column that is present in the row.
     * @private
     */
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
     * Update the cell value of a cell.
     * @param {GridColumn} column containing the cell to update.
     * @param {number} value the value to update
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

    /**
     * Add row to the section rows.
     * @param row {GridRow} the row to add.
     */
    addRow(row) {
        if (row.id in this.rows) {
            throw new Error("Row already added in section");
        }
        this.rows[row.id] = row;
        this.lastRow = row;
    }

    /**
     * Update the grand totals according to the provided column and delta.
     * @param column {GridColumn} the column the grand total has to be updated for.
     * @param delta {Number} the delta to apply on the grand totals.
     */
    updateGrandTotal(column, delta) {
        this.cells[column.id].value += delta;
        this.grandTotal += delta;
        this.grandTotalWeekendHidden += column.isWeekDay ? delta : 0;
    }
}

export class GridColumn {
    /**
     * Constructor
     *
     * @param data {Object} the grid data the column belongs to.
     * @param model {GridModel} the grid model.
     * @param title {string} the title of the column to display.
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
     * Constructor
     *
     * @param data {Object} the grid data the column belongs to.
     * @param model {GridModel} the grid model.
     * @param title {string} the title of the column to display.
     * @param dateStart {String} the date start serialized
     * @param dateEnd {String} the date end serialized
     * @param isToday {Boolean} is the date column representing today?
     * @param isWeekDay {Boolean} whether the column is not a weekend day.
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
     * Resolve the range the view opens on: the one last picked by this user for
     * this view, else the arch's default. A name read back from storage is only
     * honoured while the arch still declares it -- ranges get renamed and
     * removed, and every period getter dereferences `range` unconditionally, so
     * an unchecked stale name is a crash on mount rather than a stale scale.
     *
     * @private
     * @return {Object|undefined} the range to activate, if any.
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

    /**
     * The aggregate the readonly field is read off a group with, if the arch
     * declares one. Named once: it is asked for in `aggregates` and read back
     * in `_generateData`, and the two spellings have to agree.
     *
     * @return {string|undefined}
     */
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
     * Get fields to use in the group by or in fields of the read_group
     * @private
     * @param {Object} metaData
     * @return {string[]} list of fields name.
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
     * Split a groupby spec into the field it groups and the granularity it
     * asks for. The two are not interchangeable: read_group keys its result by
     * the whole spec (`date:month`), while fieldsInfo, the row domain and every
     * `default_` context key are about the field alone (`date`).
     *
     * @private
     * @param {string} groupBy a groupby spec, e.g. "date:month".
     * @return {{name: string, granularity: string|undefined}}
     */
    _parseGroupBy(groupBy) {
        const [name, granularity] = groupBy.split(":");
        return { name, granularity };
    }

    /**
     * The spec to send to read_group for a row or section field, and to read
     * its value back off a group with. Composed rather than stored, so a field
     * declared in the arch and a field taken from a search groupby cannot
     * disagree about what was asked for.
     *
     * @param {{name: string, granularity?: string}} field
     * @return {string}
     */
    getGroupBySpec(field) {
        return field.granularity ? `${field.name}:${field.granularity}` : field.name;
    }

    /**
     * Whether read_group answers this grouping with a `(value, label)` pair
     * rather than a bare value -- a many2one's `(id, display_name)` and a date
     * granularity's `(period start, label)` share that shape.
     *
     * @param {{name: string, granularity?: string}} field
     * @return {boolean}
     */
    isPairValued(field) {
        return Boolean(
            field.granularity || this.fieldsInfo[field.name].type === "many2one",
        );
    }

    /**
     * The identity a grouped value is keyed and filtered by, taken out of
     * whatever shape read_group answered with.
     *
     * @param {{name: string, granularity?: string}} field
     * @param {*} rawValue the value as read_group returned it.
     * @return {*}
     */
    getGroupValue(field, rawValue) {
        return this.isPairValued(field) ? rawValue && rawValue[0] : rawValue;
    }

    /**
     * The domain selecting the records of one group of `field`. A granularity
     * names a period, not a value, so it is filtered by its bounds -- writing
     * `date = "2017-01-01"` for a month group would keep one day of it.
     *
     * @private
     * @param {{name: string, granularity?: string}} field
     * @param {*} rawValue the value as read_group returned it.
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

    /**
     * Set the new range according to the range name passed into parameter.
     * @param rangeName {string} the range name to set.
     */
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

    /**
     * Move the anchor to the next/previous step
     * @param direction {"forward"|"backward"} the direction to the move the anchor
     */
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
     * Load the model
     *
     * @override
     * @param params {Object} the search parameters (domain, groupBy, etc.)
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
     * A groupby is the column field's own when it names that field, with or
     * without a granularity suffix -- `date` and `date:month` are, `date_end`
     * merely starts with the same letters and is a perfectly good row field.
     *
     * @private
     * @param {string} groupBy a groupby spec, e.g. "date:month".
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

    /**
     * Generate the date columns.
     * @private
     */
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
     * Search grid columns.
     *
     * Both parameters are an extension point and nothing here passes either:
     * `_getInitialData` calls this bare. They are the only route to a readonly
     * *column* -- `GridColumn.readonly` makes every cell under it readonly --
     * so that capability is reachable only from an override. The readonly
     * field named here is a field of the column's own relation, not the grid's
     * `readonlyField`, which is aggregated per cell out of the read_group and
     * is a different question entirely.
     *
     * @param {Array} [domain] domain to filter the columns.
     * @param {string} [readonlyField] a field of the related model marking a
     *      column readonly.
     * @returns {Array} rows of [id, display_name] or [id, display_name, readonly].
     */
    /**
     * The ORM to resolve the column axis with. A grid's columns are metadata --
     * a selection's values, or the records of the relation -- and not sampled
     * content; only the rows are sampled. A SampleServer can serve neither:
     * it is built for one model and knows seven routes, so the many2one
     * lookup dies on the route (`search_read` is not among them, and
     * `UnimplementedRouteError` carries no message at all) and the selection
     * lookup dies a step earlier still, on the model, since
     * `ir.model.fields` is not the one it was built for. Either way the
     * sample reload throws and the view never mounts.
     *
     * @private
     * @return {Object} the orm service, never the sample one.
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

    /**
     * Initialize the data.
     * @private
     */
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
     * Gets additional groups to be added to the grid. The call to this function is made in parallel to the main data
     * fetching.
     *
     * This function is intended to be overriden in modules where we want to display additional sections and/or rows in
     * the grid than what would be returned by the formattedReadGroup.
     * The model `sectionField` and `rowFields` can be used in order to know what need to be returned.
     *
     * An example of this is:
     * - when considering timesheet, we want to ease their encoding by adding (to the data that is fetched for scale),
     *   the entries that have been entered the week before. That way, the first day of week
     *   (or month, depending on the scale), a line is already displayed with 0's and can directly been used in the
     *   grid instead of having to use the create button.
     *
     * @return {Array<Promise<Object>>} an array of Promise of Object of type:
     *                                      {
     *                                          sectionKey: {
     *                                              value: Any,
     *                                              rows: {
     *                                                  rowKey: {
     *                                                      domain: Domain,
     *                                                      values: [Any],
     *                                                  },
     *                                              },
     *                                          },
     *                                      }
     * @private
     */
    _fetchAdditionalData(metaData) {
        return [];
    }

    /**
     * Gets additional groups to be added to the grid. The call to this function is made after the main data fetching
     * has been processed which allows using `data` in the code.
     * This function is intended to be overriden in modules where we want to display additional sections and/or rows in
     * the grid than what would be returned by the formattedReadGroup.
     * The model `sectionField`, `rowFields` as well as `data` can be used in order to know what need to be returned.
     *
     * @return {Array<Promise<Object>>} an array of Promise of Object of type:
     *                                      {
     *                                          sectionKey: {
     *                                              value: Any,
     *                                              rows: {
     *                                                  rowKey: {
     *                                                      domain: Domain,
     *                                                      values: [Any],
     *                                                  },
     *                                              },
     *                                          },
     *                                      }
     * @private
     */
    _postFetchAdditionalData(metaData) {
        return [];
    }

    _getAdditionalPromises(metaData) {
        return this.usesUnavailability ? [this._fetchUnavailabilityDays(metaData)] : [];
    }

    /**
     * Whether this grid renders unavailability at all. `grid_unavailability`
     * answers `{}` on `base` and `_processUnavailabilityDays` drops it on the
     * floor, so asking for it by default costs every grid in the database a
     * round trip whose result nothing reads -- and costs every test of one a
     * stub for a route it never wanted. A model that displays unavailability
     * turns it on.
     *
     * @return {boolean}
     */
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
     * Store what `grid_unavailability` answered, for a renderer to shade cells
     * with.
     *
     * Put it on `metaData`, not on the model: `load` publishes metaData with
     * one `Object.assign` once `keepLast` has decided this load is the current
     * one, and that is what makes a superseded load's work harmless. This was
     * the only extension point handed no metaData, and so the only one whose
     * result could outlive the load that asked for it -- two reloads in quick
     * succession, and whichever `grid_unavailability` answered last shaded the
     * grid, regardless of which load was on screen.
     *
     * @param {Object} result what the server answered.
     * @param {Object} metaData the load this result belongs to.
     */
    _processUnavailabilityDays(result, metaData) {}

    /**
     * Generate the row key according to the provided read group result.
     * @param readGroupResult {Array} the read group result the key has to be generated for.
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
     * The key a row is filed under, from the identity of each of its groups
     * rather than from a read_group answer: a consumer holding a record's
     * plain values -- the timesheet timer's, say -- finds the record's row
     * without re-spelling the key's format.
     *
     * @param {Object} values group identity per field name: a many2one's id,
     *      a selection's key, `false` for an unset one.
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
     * The value read_group answered for `field`, as it answered it, or `false`
     * for a group that was not asked to group by it -- an additional row
     * built from another model's records carries only the fields it has.
     *
     * @private
     * @param {Object} readGroupResult one group of a read_group.
     * @param {{name: string, granularity?: string}} field
     * @return {*}
     */
    _getGroupRawValue(readGroupResult, field) {
        const spec = this.getGroupBySpec(field);
        return spec in readGroupResult && readGroupResult[spec];
    }

    /**
     * The key of the column a group belongs to: the id a many2one or date
     * column was mapped by, the value of a selection one.
     *
     * @private
     * @param {Object} readGroupResult one group of a read_group.
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
     * Generate the section key
     * @param readGroupResult
     * @private
     */
    _generateSectionKey(readGroupResult, sectionField) {
        const rawValue = readGroupResult[this.getGroupBySpec(sectionField)];
        return this._composeSectionKey(this.getGroupValue(sectionField, rawValue));
    }

    /**
     * Generate the row domain for the provided read group result.
     * @param readGroupResult {Array} the read group result the domain has to be generated for.
     * @return {{domain: Domain, values: Object}} the generated domain and values.
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

    /**
     * The single valueless section a grid without a section field hangs every
     * row under. Idempotent: `_generateData` needs the same one for every
     * group, and used to get it by carrying the local from one loop iteration
     * to the next -- which answered `undefined` for the first group the moment
     * anything else had already put a section in `data`.
     *
     * @private
     */
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

    /**
     * Method meant to be overridden whenever an item (row and section) post process is needed.
     * @param item {GridSection|GridRow}
     */
    _itemsPostProcess(item, metaData) {}
}
