/** @odoo-module native */
import {
    Component,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    proxy,
    untrack,
    useListener,
    useProps,
} from "@odoo/owl";
import { useCallbackRecorder } from "@web/core/action_hook";
import { hasTouch, isMobileOS } from "@web/core/browser/feature_detection";
import { getColorIndex } from "@web/core/colors/colors";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import {
    compareDates,
    formatValue,
    now,
    toDateTime,
    today,
} from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { is24HourFormat } from "@web/core/l10n/time";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { omit } from "@web/core/utils/collections/objects";
import { KeepLast } from "@web/core/utils/concurrency";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { onWillRender } from "@web/core/utils/render_hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { debounce } from "@web/core/utils/timing";
import { url } from "@web/core/utils/urls";
import { useVirtualGrid } from "@web/core/utils/virtual_grid";
import { useReactiveModel } from "@web/model/model";
import { useGanttContext } from "@web_gantt/gantt_context";

import { visibleColumns } from "./gantt_columns.js";
import { GridGeometry } from "./gantt_grid_geometry.js";
import { diffColumn, getCellColor, localStartOf } from "./gantt_helpers.js";
import {
    assignPillLevels,
    colsTemplate,
    columnWidths,
    focusFactorAt,
    rowsTemplate,
    subColumnsDistance,
} from "./gantt_layout.js";
import {
    computeFoldableColumns,
    computeFoldedGrid,
    coveredSlots,
} from "./gantt_off_hours.js";
import {
    durationLabel,
    pillBounds,
    pillDecorationClasses,
    pillLabel,
} from "./gantt_pill.js";

/**
 * @typedef {`__connector__${number | "new"}`} ConnectorId
 * @typedef {import("./gantt_connector").ConnectorProps} ConnectorProps
 * @typedef {Temporal.ZonedDateTime} DateTime
 * @typedef {"copy" | "reschedule"} DragActionMode
 * @typedef {"drag" | "locked" | "resize"} InteractionMode
 * @typedef {`__pill__${number}`} PillId
 * @typedef {import("./gantt_model").RowId} RowId
 *
 * @typedef Column
 * @property {number} index
 * @property {GridPosition} grid
 * @property {boolean} [isToday]
 * @property {DateTime} start
 * @property {DateTime} stop
 *
 * @typedef GridPosition
 * @property {number | number[]} [row]
 * @property {number | number[]} [column]
 *
 * @typedef Group
 * @property {boolean} break
 * @property {number} col
 * @property {Pill[]} pills
 * @property {number} aggregateValue
 * @property {GridPosition} grid
 *
 * @typedef GanttRendererProps
 * @property {import("./gantt_model").GanttModel} model
 * @property {Document} arch
 * @property {string} class
 * @property {(context: Record<string, any>)} create
 * @property {{ content?: Point }} [scrollPosition]
 * @property {{ el: HTMLDivElement | null }} [contentRef]
 *
 * @typedef HoveredInfo
 * @property {Element | null} connector
 * @property {HTMLElement | null} hoverable
 * @property {HTMLElement | null} pill
 *
 * @typedef Interaction
 * @property {InteractionMode | null} mode
 * @property {DragActionMode} dragAction
 *
 * @typedef Pill
 * @property {PillId} id
 * @property {boolean} disableStartResize
 * @property {boolean} disableStopResize
 * @property {number} leftMargin
 * @property {number} level
 * @property {string} name
 * @property {DateTime} startDate
 * @property {DateTime} stopDate
 * @property {GridPosition} grid
 * @property {RelationalRecord} record
 * @property {number} _color
 * @property {number} _progress
 *
 * @typedef Point
 * @property {number} [x]
 * @property {number} [y]
 *
 * @typedef {Record<string, any>} RelationalRecord
 * @property {number | false} id
 *
 * @typedef ResizeBadge
 * @property {Point & { right?: number }} position
 * @property {number} diff
 * @property {string} scale
 *
 * @typedef {import("./gantt_model").Row & {
 *  grid: GridPosition,
 *  pills: Pill[],
 *  cellColors?: Record<string, string>,
 *  thumbnailUrl?: string,
 *  avatar?: Record<string, unknown> | null
 * }} Row
 *
 * @typedef SubColumn
 * @property {number} columnIndex
 * @property {boolean} [isToday]
 * @property {DateTime} start
 * @property {DateTime} stop
 */

const clearObject = (obj) => {
    for (const key in obj) {
        delete obj[key];
    }
};
export const rtl = () => localization.direction === "rtl";

const log = makeLogger("gantt.renderer");

export class GanttRendererCore extends Component {
    props = useProps(this.constructor.props);
    render = useRender();

    setup() {
        this.ganttContext = useGanttContext();
        useLifecycleLog(log);
        this.model = useReactiveModel(this.props.model);

        this.gridRef = elementRef();
        this.cellContainerRef = elementRef();

        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        this.notificationService = useService("notification");
        this.orm = useService("orm");
        this.viewService = useService("view");

        this.keepLast = new KeepLast();

        this.defaultkanbanViewParams = null;

        this.is24HourFormat = is24HourFormat();

        this.progressBarsReactive = proxy({ hoveredRowId: null });
        /** @type {Object[]} */
        this.columnsGroups = [];
        /** @type {Column[]} */
        this.columns = [];
        /** @type {Pill[]} */
        /** @type {Record<PillId, Pill>} */
        this.pills = {}; // mapping to retrieve pills from pill ids
        /** @type {Row[]} */
        this.rows = [];
        /** @type {SubColumn[]} */
        this.subColumns = [];
        /** @type {Record<RowId, Pill[]>} */
        this.rowPills = {};

        /** @type {GridGeometry | null} rebuilt whenever the range or scale changes */
        this.geometry = null;
        this.controlsCallbacks = {
            focusToday: () => this.focusToday(),
            getCurrentFocusDate: () => this.getCurrentFocusDate(),
        };
        this.offHoursState = proxy({});
        useListener(
            window,
            "resize",
            debounce(() => {
                this.shouldComputeSomeWidths = true;
                this.render();
            }, 100),
        );
        onWillStart(() => this.computeDerivedParams());
        onWillUpdateProps(this.computeDerivedParams);

        this.virtualGrid = useVirtualGrid({
            scrollableRef: this.props.contentRef,
            initialScroll: this.props.scrollPosition?.content,
            bufferCoef: 0.1,
            onChange: (changed) => {
                if ("columnsIndexes" in changed) {
                    this.shouldComputeGridColumns = true;
                }
                if ("rowsIndexes" in changed) {
                    this.shouldComputeGridRows = true;
                }
                this.render();
            },
        });

        onWillRender(this.onWillRender);
        onWillUnmount(this.onWillUnmount);
        useLayoutEffect(() => {
            if (this.useFocusDate) {
                this.useFocusDate = false;
                this.focusDate(this.model.metaData.focusDate);
            }
        });

        useCallbackRecorder(
            this.ganttContext.getCurrentFocusDateCallBackRecorder,
            this.getCurrentFocusDate.bind(this),
        );
    }

    get foldedGridColumnCount() {
        return this.offHoursState.foldedGridColumnSpans?.length ?? this.columnCount;
    }

    get controlsProps() {
        return {
            displayExpandCollapseButtons: this.rows[0]?.isGroup, // all rows on same level have same type
            model: this.model,
            ...this.controlsCallbacks,
        };
    }

    /**
     * @returns {boolean}
     */
    get hasRowHeaders() {
        const { groupedBy } = this.model.metaData;
        const { displayMode } = this.model.displayParams;
        return groupedBy.length > 0 || displayMode === "sparse";
    }

    /**
     * @returns {boolean}
     */
    get isTouchDevice() {
        return isMobileOS() || hasTouch();
    }

    addStickyCoordinates(rows, columns) {
        this.stickyGridRows = Object.assign(
            {},
            ...rows.map((row) => ({ [row]: true })),
        );
        this.stickyGridColumns = Object.assign(
            {},
            ...columns.map((column) => ({ [column]: true })),
        );
        this.setSomeGridStyleProperties();
    }

    removeStickyCoordinates() {
        this.stickyGridRows = {};
        this.stickyGridColumns = {};
        this.setSomeGridStyleProperties();
    }

    /**
     *
     * @param {Object} param
     * @param {Object} param.grid
     */
    addCoordinatesToCoarseGrid({ grid }) {
        if (grid.row) {
            this.coarseGridRows[this.getFirstGridRow({ grid })] = true;
            this.coarseGridRows[this.getLastGridRow({ grid })] = true;
        }
        if (grid.column) {
            this.coarseGridCols[this.getFirstGridCol({ grid })] = true;
            this.coarseGridCols[this.getLastGridCol({ grid })] = true;
        }
    }

    /**
     * @param {Pill} pill
     * @param {Group} group
     */
    addTo(pill, group) {
        group.pills.push(pill);
        group.aggregateValue++; // pill count
        return true;
    }

    /**
     * @param {Row} row
     * @param {Group} group
     * @returns {boolean}
     */
    shouldAggregate(row, group) {
        return Boolean(group.pills.length);
    }

    /**
     * @param {Pill[]} pills
     * @param {Row} row
     */
    aggregatePills(pills, row) {
        /** @type {Record<number, Group>} */
        const groups = {};
        function getGroup(col) {
            if (!(col in groups)) {
                groups[col] = {
                    break: false,
                    col,
                    pills: [],
                    aggregateValue: 0,
                    grid: { column: [col, col + 1] },
                };
            }
            return groups[col];
        }

        const lastCol = this.columnCount * this.model.metaData.scale.cellPart + 1;
        for (const pill of pills) {
            let addedInPreviousCol = false;
            let col;
            for (
                col = this.getFirstGridCol(pill);
                col < this.getLastGridCol(pill);
                col++
            ) {
                const group = getGroup(col);
                const added = this.addTo(pill, group);
                if (addedInPreviousCol !== added) {
                    group.break = true;
                }
                addedInPreviousCol = added;
            }
            // here col = this.getLastGridCol(pill)
            if (addedInPreviousCol && col < lastCol) {
                const group = getGroup(col);
                group.break = true;
            }
        }

        const filteredGroups = Object.values(groups).filter((g) =>
            this.shouldAggregate(row, g),
        );

        if (this.shouldMergeGroups()) {
            return this.mergeGroups(filteredGroups);
        }

        return filteredGroups;
    }

    /**
     * @param {Pill[]} pills -- sorted by first column; each gets its `level`
     * @returns {number} how many levels the row needs
     */
    calculatePillsLevel(pills) {
        return assignPillLevels(pills);
    }

    computeVisibleColumns() {
        const [firstIndex, lastIndex] = this.virtualGrid.columnsIndexes;
        const { displayUnavailability, globalStart, globalStop, scale } =
            this.model.metaData;
        this.subColumnsKey = `${firstIndex}_${lastIndex}`;
        ({
            columns: this.columns,
            subColumns: this.subColumns,
            columnsGroups: this.columnsGroups,
            coarseGridCols: this.coarseGridCols,
        } = visibleColumns({
            firstIndex,
            lastIndex,
            columnCount: this.columnCount,
            scale,
            globalStart,
            globalStop,
            displayUnavailability,
            foldedGridColumnSpans: this.offHoursState.foldedGridColumnSpans,
            foldedColumns: this.offHoursState.foldedColumns,
            foldableColumnsMapping: this.foldableColumnsMapping,
            indexInTotalGrid: (index) => this.getIndexInTotalGrid(index),
            geometry: this.geometry,
            now: now(),
        }));
    }

    computeVisibleRows() {
        this.coarseGridRows = {
            1: true,
            [this.getLastGridRow(this.rows[this.rows.length - 1])]: true,
        };
        const [rowStart, rowEnd] = this.virtualGrid.rowsIndexes;
        this.rowsToRender = new Set();
        for (const row of this.rows) {
            const [first, last] = row.grid.row;
            if (last <= rowStart + 1 || first > rowEnd + 1) {
                continue;
            }
            this.addToRowsToRender(row);
        }
    }

    getIndexInTotalGrid(index) {
        return (
            this.offHoursState.mappingFoldedGridToTotalGridColumnIndex?.get(index) ??
            index
        );
    }

    getColNumberInFoldedGrid(num) {
        return (
            this.offHoursState.mappingTotalGridToFoldedGridSubColumns?.get(num) ?? num
        );
    }

    getFirstGridCol({ grid }) {
        const [first] = grid.column;
        return first;
    }

    getLastGridCol({ grid }) {
        const [, last] = grid.column;
        return last;
    }

    getFirstGridRow({ grid }) {
        const [first] = grid.row;
        return first;
    }

    getLastGridRow({ grid }) {
        const [, last] = grid.row;
        return last;
    }

    addToPillsToRender(pill) {
        this.pillsToRender.add(pill);
        this.addCoordinatesToCoarseGrid(pill);
    }

    addToRowsToRender(row) {
        this.rowsToRender.add(row);
        const [first, last] = row.grid.row;
        for (let i = first; i <= last; i++) {
            this.coarseGridRows[i] = true;
        }
    }

    /**
     * give bounds only
     */
    getVisibleCols() {
        const [firstIndex, lastIndex] = this.virtualGrid.columnsIndexes;
        const startIndex = this.getIndexInTotalGrid(firstIndex);
        const endIndex = this.getIndexInTotalGrid(lastIndex);
        const { cellPart } = this.model.metaData.scale;
        const firstVisibleCol = 1 + cellPart * startIndex;
        const lastVisibleCol = 1 + cellPart * (endIndex + 1);
        return [firstVisibleCol, lastVisibleCol];
    }

    /**
     * give bounds only
     */
    getVisibleRows() {
        const [firstIndex, lastIndex] = this.virtualGrid.rowsIndexes;
        const firstVisibleRow = firstIndex + 1;
        const lastVisibleRow = lastIndex + 1;
        return [firstVisibleRow, lastVisibleRow];
    }

    computeVisiblePills() {
        const endVisible = log.perf("computeVisiblePills");
        this.pillsToRender = new Set();

        const [firstVisibleCol, lastVisibleCol] = this.getVisibleCols();
        const [firstVisibleRow, lastVisibleRow] = this.getVisibleRows();

        const isOut = (pill, filterOnRow = true) =>
            this.getFirstGridCol(pill) > lastVisibleCol ||
            this.getLastGridCol(pill) < firstVisibleCol ||
            (filterOnRow &&
                (this.getFirstGridRow(pill) > lastVisibleRow ||
                    this.getLastGridRow(pill) - 1 < firstVisibleRow));

        const getRowPills = (row, filterOnRow) =>
            (this.rowPills[row.id] || []).filter((pill) => !isOut(pill, filterOnRow));

        for (const row of this.rowsToRender) {
            for (const rowPill of getRowPills(row)) {
                this.addToPillsToRender(rowPill);
            }
            if (
                !row.isGroup &&
                row.unavailabilities?.length &&
                row.cellColorsFor !== this.subColumnsKey
            ) {
                // The colours depend on the visible sub-columns and the row's
                // unavailabilities only; a vertical scroll changes neither.
                row.cellColors = this.getRowCellColors(row);
                row.cellColorsFor = this.subColumnsKey;
            }
        }

        if (this.stickyPillId) {
            this.addToPillsToRender(this.pills[this.stickyPillId]);
        }

        if (this.totalRow) {
            this.totalRow.pills = getRowPills(this.totalRow, false);
            for (const pill of this.totalRow.pills) {
                this.addCoordinatesToCoarseGrid({ grid: omit(pill.grid, "row") });
            }
        }
        endVisible({ pills: this.pillsToRender.size, rows: this.rowsToRender?.size });
    }

    getRowFromPill(pill) {
        return this.rowByIds[pill.rowId];
    }

    getColInCoarseGridKeys() {
        return Object.keys({ ...this.coarseGridCols, ...this.stickyGridColumns });
    }

    getRowInCoarseGridKeys() {
        return Object.keys({ ...this.coarseGridRows, ...this.stickyGridRows });
    }

    computeColsTemplate() {
        return colsTemplate(this.getColInCoarseGridKeys(), (x, y) =>
            this.getSubColumnsDistance(x, y, this.cellPartWidth),
        );
    }

    getSubColumnsDistance(start, stop, cellPartWidth) {
        return subColumnsDistance(start, stop, {
            cellPart: this.model.metaData.scale.cellPart,
            cellPartWidth,
            foldedGridColumnSpans: this.offHoursState.foldedGridColumnSpans,
            foldedColumns: this.offHoursState.foldedColumns,
            colNumberInFoldedGrid: (col) => this.getColNumberInFoldedGrid(col),
            indexInTotalGrid: (i) => this.getIndexInTotalGrid(i),
        });
    }

    computeRowsTemplate() {
        return rowsTemplate(this.getRowInCoarseGridKeys(), this.gridRows);
    }

    computeSomeWidths() {
        const { cellPart, minimalColumnWidth } = this.model.metaData.scale;
        // measured from onWillRender: a tracked read of the ref would render
        // again as soon as the content binds it
        this.contentRefWidth =
            untrack(() => this.props.contentRef.el)?.clientWidth ??
            document.body.clientWidth;
        this.rowHeaderWidth = this.hasRowHeaders
            ? this.constructor.getRowHeaderWidth(this.contentRefWidth)
            : 0;
        const widths = columnWidths({
            contentWidth: this.contentRefWidth,
            rowHeaderWidth: this.rowHeaderWidth,
            cellPart,
            minimalColumnWidth,
            columnCount: this.columnCount,
            foldedGridColumnCount: this.foldedGridColumnCount,
            foldedColumns: this.offHoursState.foldedColumns,
        });
        this.visibleCellContainerWidth = widths.visibleCellContainerWidth;
        this.cellPartWidth = widths.cellPartWidth;
        this.columnWidth = widths.columnWidth;
        this.totalWidth = widths.totalWidth;
        this.columnWidths = widths.columnWidths;
        this.virtualGrid.setColumnsWidths(widths.columnWidths);
    }

    computeDerivedParams() {
        const endDerive = log.perf("computeDerivedParams");
        // Stamp what this build was derived from. `onWillRender` compares the
        // model's epoch against it, so the derived params rebuild when the model
        // changed and not merely when the component re-rendered.
        this._builtFromEpoch = this.model.updateEpoch;
        const { rows: modelRows } = this.model.data;

        const {
            displayUnavailability,
            globalStart,
            globalStop,
            scale,
            startDate,
            stopDate,
        } = this.model.metaData;
        this.columnCount = diffColumn(globalStart, globalStop, scale.interval);
        if (
            !this.currentStartDate ||
            diffColumn(this.currentStartDate, startDate, "day") ||
            diffColumn(this.currentStopDate, stopDate, "day") ||
            this.currentScaleId !== scale.id
        ) {
            this.useFocusDate = true;
            this.geometry = new GridGeometry(globalStart, scale);
            delete this.offHoursState.foldedColumns;
        }
        this.currentStartDate = startDate;
        this.currentStopDate = stopDate;
        this.currentScaleId = scale.id;

        this.currentGridRow = 1;
        this.gridRows = [];
        this.nextPillId = 1;

        this.pills = {}; // mapping to retrieve pills from pill ids
        this.rows = [];
        this.rowPills = {};
        this.rowByIds = {};

        const prePills = this.getPills();
        this.prePillByRecordId = new Map(
            prePills.map((pill, index) => [pill.record.id, { index, pill }]),
        );
        for (const row of modelRows) {
            this.rows.push(...this.processRow(row).rows);
        }

        const { displayTotalRow } = this.model.metaData;
        if (displayTotalRow) {
            this.totalRow = this.getTotalRow(prePills);
        }
        if (this.containsReadonlyGroup()) {
            this.setupInitialReadonly();
        }

        // The rows are built; the connector and multi-create indexes are
        // derived from them rather than written as each row goes by.
        this.indexPillsForMultiCreate();
        if (this.shouldRenderConnectors()) {
            this.indexPillsForConnectors();
            this.initializeConnectors();
            this.generateConnectors();
        }

        if (displayUnavailability) {
            this.computeUnavailabilityPeriods();
            this.computeFoldedGrid();
        }
        this.shouldComputeSomeWidths = true;
        this.shouldComputeGridColumns = true;
        this.shouldComputeGridRows = true;
        endDerive({
            epoch: this._builtFromEpoch,
            rows: this.rows?.length,
            columns: this.columnCount,
            pills: Object.keys(this.pills || {}).length,
        });
    }

    enrichPill(pill) {
        const { colorField, fields, pillDecorations, progressField } =
            this.model.metaData;

        pill.displayName = this.getDisplayName(pill);

        const classes = pillDecorations
            ? pillDecorationClasses(pill.record, fields, pillDecorations, user.context)
            : [];

        if (colorField) {
            pill._color = getColorIndex(pill.record[colorField]);
            classes.push(`o_gantt_color_${pill._color}`);
        }

        if (progressField) {
            pill._progress = pill.record[progressField] || 0;
        }

        pill.className = classes.join(" ");

        return pill;
    }

    focusDate(date, focusGroup = true) {
        const { globalStart, globalStop, scale } = this.model.metaData;
        const { cellPart, interval, unit } = scale;
        const focusedDate = focusGroup ? localStartOf(date, unit) : date;
        const diff = focusedDate.epochMilliseconds - globalStart.epochMilliseconds;
        const totalDiff = globalStop.epochMilliseconds - globalStart.epochMilliseconds;
        const factor = diff / totalDiff;
        if (!focusGroup && (factor < 0 || 1 < factor)) {
            return false;
        }
        const rtlFactor = rtl() ? -1 : 1;
        if (this.columnCount === this.foldedGridColumnCount) {
            const scrollLeft = factor * this.cellContainerRef.el.clientWidth;
            this.props.contentRef.el.scrollLeft = rtlFactor * scrollLeft;
            return true;
        }
        const { column, delta } = this.getSubColumnFromDate(focusedDate);
        const col = 1 + diffColumn(globalStart, column, interval) * cellPart + delta;
        const { distance } = this.getSubColumnsDistance(1, col, this.cellPartWidth);
        this.props.contentRef.el.scrollLeft = rtlFactor * distance;
        return true;
    }

    /**
     * @param {DateTime} date
     * @param {string} format
     * @returns {string}
     */
    formatDate(date, format) {
        return formatValue(date, format);
    }

    focusFirstPill(rowId) {
        const pill = this.rowPills[rowId][0];
        if (pill) {
            const col = this.getFirstGridCol(pill);
            const { start: date } = this.getColumnFromColNumber(col);
            this.focusDate(date);
        }
    }

    focusToday() {
        return this.focusDate(toDateTime(today()), false);
    }

    /**
     * @param {Group} group
     * @param {Group} previousGroup
     */
    getAggregateValue(group, previousGroup) {
        // both groups have the same pills by construction
        // here the aggregateValue is the pill count
        return group.aggregateValue;
    }

    /**
     * @param {number} startCol
     * @param {number} stopCol
     */
    getColumnStartStop(startCol, stopCol) {
        const { start } = this.getColumnFromColNumber(startCol);
        const { stop } = this.getColumnFromColNumber(stopCol);
        return { start, stop };
    }

    /**
     * @param {Row} row
     * @param {Column} column
     * @return {Object}
     */
    ganttCellAttClass(row, column) {
        return {
            o_sample_data_disabled: this.isDisabled(row),
            o_gantt_today: column.isToday,
            o_gantt_cell_folded: column.isFolded,
            o_gantt_group: row.isGroup,
            o_gantt_hoverable: this.isHoverable(row),
            o_group_open: !this.model.isClosed(row.id),
            o_gantt_readonly: row.readonly,
        };
    }

    getCurrentFocusDate() {
        const { globalStart, globalStop } = this.model.metaData;
        const rtlFactor = rtl() ? -1 : 1;
        const cellGridMiddleX =
            rtlFactor * this.props.contentRef.el.scrollLeft +
            (this.contentRefWidth + this.rowHeaderWidth) / 2;
        const factor = focusFactorAt(cellGridMiddleX - this.rowHeaderWidth, {
            cellContainerWidth: this.cellContainerRef.el.clientWidth,
            columnWidths: this.columnWidths,
            columnCount: this.columnCount,
            indexInTotalGrid: (i) => this.getIndexInTotalGrid(i),
        });
        const totalDiff = globalStop.epochMilliseconds - globalStart.epochMilliseconds;
        return globalStart.add({ milliseconds: Math.round(factor * totalDiff) });
    }

    getDisplayName(pill) {
        const { computePillDisplayName, dateStartField, dateStopField, scale } =
            this.model.metaData;
        const { record } = pill;
        if (!computePillDisplayName) {
            return record.display_name;
        }
        const duration = this.getPillDuration(record);
        return pillLabel({
            displayName: record.display_name,
            startDate: toDateTime(record[dateStartField]),
            stopDate: toDateTime(record[dateStopField]),
            scaleId: scale.id,
            rangeStart: this.currentStartDate,
            rangeStop: this.currentStopDate,
            duration,
            durationStr: duration ? this.getDurationStr(record) : "",
        });
    }

    /**
     * How long the pill's record lasts, in the unit `getDurationStr` formats.
     * `0` when the view declares no `duration_field`: the gantt view itself has
     * no notion of a duration, it only relays the one the arch names.
     *
     * @param {RelationalRecord} record
     * @returns {number}
     */
    getPillDuration(record) {
        const { durationField } = this.model.metaData;
        return (durationField && record[durationField]) || 0;
    }

    getDurationStr(record) {
        return durationLabel(this.getPillDuration(record));
    }

    /**
     * @param {Pill} pill
     */
    getGroupPillDisplayName(pill) {
        return pill.aggregateValue;
    }

    /**
     * @param {{ column?: [number, number], row?: [number, number] }} position
     */
    getGridPosition({ column, row }) {
        const style = [];
        if (column) {
            style.push(`grid-column:c${column[0]}/c${column[1]}`);
        }
        if (row) {
            style.push(`grid-row:r${row[0]}/r${row[1]}`);
        }
        return style.join(";");
    }

    /**
     * @param {{ column?: [number, number], row?: [number, number] }} position
     */
    getGroupHeaderStyle(position) {
        return (
            this.getGridPosition(position) +
            `;max-width: ${this.visibleCellContainerWidth}px`
        );
    }

    getGridTemplateProperties() {
        return {
            "--Gantt__GridRows-grid-template-rows": this.computeRowsTemplate(),
            "--Gantt__GridColumns-grid-template-columns": this.computeColsTemplate(),
        };
    }

    setSomeGridStyleProperties() {
        for (const [name, value] of Object.entries(this.getGridTemplateProperties())) {
            this.gridRef.el.style.setProperty(name, value);
        }
    }

    getGridStyle() {
        const style = {
            "--Gantt__RowHeader-width": `${this.rowHeaderWidth}px`,
            ...this.getGridTemplateProperties(),
        };
        if (this.totalWidth !== null) {
            style.width = `${this.totalWidth}px`;
        }
        return Object.entries(style)
            .map((entry) => entry.join(":"))
            .join(";");
    }

    getPill(record) {
        const {
            canEdit,
            dateStartField,
            dateStopField,
            disableDrag,
            globalStart,
            globalStop,
        } = this.model.metaData;
        const bounds = pillBounds(record, {
            dateStartField,
            dateStopField,
            stopIsDate: this.model.dateStopFieldIsDate(),
            globalStart,
            globalStop,
            canEdit,
            disableDrag,
        });
        /** @type {Partial<Pill>} */
        return {
            disableDrag: bounds.disableDrag,
            disableStartResize: bounds.disableStartResize,
            disableStopResize: bounds.disableStopResize,
            grid: { column: this.getGridColumnFromDates(bounds.start, bounds.stop) },
            record,
        };
    }

    getColumnIndexFromDate(column) {
        return this.geometry.columnIndexFromDate(column);
    }

    getGridColumnFromDates(startDate, stopDate) {
        return this.geometry.gridColumnFromDates(startDate, stopDate);
    }

    getSubColumnFromDate(date, onLeft = true) {
        return this.geometry.subColumnFromDate(date, onLeft);
    }

    getSubColumnFromColNumber(col) {
        return this.geometry.subColumnFromColNumber(col);
    }

    getColumnIndexFromColNumber(col) {
        return this.geometry.columnIndexFromColNumber(col);
    }

    getColumnFromColNumber(col) {
        return this.geometry.columnFromColNumber(col);
    }

    /**
     * @param {PillId} pillId
     */
    getPillEl(pillId) {
        return this.getPillWrapperEl(pillId).querySelector(".o_gantt_pill");
    }

    /**
     * @param {Object} group
     * @param {boolean} consolidate
     */
    getPillFromGroup(group, consolidate) {
        const { excludeField, field, maxValue } =
            this.model.metaData.consolidationParams;

        const newPill = {
            id: `__pill__${this.nextPillId++}`,
            level: 0,
            aggregateValue: group.aggregateValue,
            grid: group.grid,
        };

        // Enrich the aggregates with consolidation data
        if (consolidate && field) {
            newPill.consolidationValue = 0;
            for (const pill of group.pills) {
                if (!pill.record[excludeField]) {
                    newPill.consolidationValue += pill.record[field];
                }
            }
            newPill.consolidationMaxValue = maxValue;
            newPill.consolidationExceeded =
                newPill.consolidationValue > newPill.consolidationMaxValue;
        }

        if (consolidate && maxValue) {
            const status = newPill.consolidationExceeded ? "danger" : "success";
            newPill.className = `bg-${status} border-${status}`;
            newPill.displayName = newPill.consolidationValue;
        } else {
            newPill.displayName = this.getGroupPillDisplayName(newPill);
        }

        return newPill;
    }

    /**
     * There are two forms of pills: pills comming from fetched records
     * and pills that are some kind of aggregation of the previous.
     *
     * Here we create the pills of the firs type.
     *
     * The basic properties (independent of rows,...) of the pills of
     * the first type should be computed here.
     *
     * @returns {Partial<Pill>[]}
     */
    getPills() {
        const { records } = this.model.data;
        const { dateStartField } = this.model.metaData;
        const pills = [];
        for (const record of records) {
            const pill = this.getPill(record);
            pills.push(this.enrichPill(pill));
        }
        return pills.sort(
            (p1, p2) =>
                p1.grid.column[0] - p2.grid.column[0] ||
                compareDates(
                    toDateTime(p1.record[dateStartField]),
                    toDateTime(p2.record[dateStartField]),
                ),
        );
    }

    /**
     * @param {PillId} pillId
     */
    getPillWrapperEl(pillId) {
        const pillSelector = `:scope > [data-pill-id="${pillId}"]`;
        return this.cellContainerRef.el?.querySelector(pillSelector);
    }

    /**
     * @param {Row} row
     */
    getProgressBarProps(row) {
        return {
            progressBar: row.progressBar,
            reactive: this.progressBarsReactive,
            rowId: row.id,
        };
    }

    /**
     * @param {Row} row
     */
    getRowCellColors(row) {
        const { cellPart } = this.model.metaData.scale;
        const covered = coveredSlots(this.subColumns, row.unavailabilities);
        /** @type {Record<string, string>} */
        const cellColors = {};
        for (let j = 0; j < covered.length; j += cellPart) {
            const { isToday, columnIndex } = this.subColumns[j];
            const style = getCellColor(
                cellPart,
                covered.slice(j, j + cellPart),
                isToday,
            );
            if (style) {
                cellColors[columnIndex] = style;
            }
        }
        return cellColors;
    }

    getFromData(groupedByField, resId, key, defaultVal) {
        const values = this.model.data[key];
        if (groupedByField) {
            return values[groupedByField]?.[resId ?? false] || defaultVal;
        }
        return values.__default?.false || defaultVal;
    }

    /**
     * @param {string} [groupedByField]
     * @param {false|number} [resId]
     * @returns {Object}
     */
    /**
     * The props of the `Avatar` component drawn in the row header instead of
     * the row name, or null for the name. The base registers no such
     * component: a subclass returning props here adds one to its
     * `components`.
     *
     * @param {Row} row
     * @returns {Record<string, unknown> | null}
     */
    getRowAvatar(row) {
        return null;
    }

    getRowProgressBar(groupedByField, resId) {
        return this.getFromData(groupedByField, resId, "progressBars", null);
    }

    /**
     * @param {string} [groupedByField]
     * @param {false|number} [resId]
     * @returns {{ start: DateTime, stop: DateTime }[]}
     */
    getRowUnavailabilities(groupedByField, resId) {
        return this.getFromData(groupedByField, resId, "unavailabilities", []);
    }

    /**
     * @param {"t0" | "t1" | "t2"} type
     * @returns {number}
     */
    getRowTypeHeight(type) {
        return { t0: 24, t1: 25, t2: 10 }[type];
    }

    getRowTitleStyle(row) {
        return `grid-column: ${row.groupLevel + 2} / -1`;
    }

    /**
     * @param {Pill[]} pills
     */
    getTotalRow(pills) {
        const preRow = {
            groupLevel: 0,
            id: "[]",
            rows: [],
            name: _t("Total"),
            recordIds: pills.map(({ record }) => record.id),
        };

        this.currentGridRow = 1;
        const result = this.processRow(preRow);
        const [totalRow] = result.rows;
        const allPills = this.rowPills[totalRow.id] || [];
        const maxAggregateValue = Math.max(...allPills.map((p) => p.aggregateValue));

        totalRow.factor = maxAggregateValue > 0 ? 90 / maxAggregateValue : 0;

        return totalRow;
    }

    isPillSmall(pill) {
        const columnSpan = pill.grid.column[1] - pill.grid.column[0];
        return this.cellPartWidth * columnSpan < String(pill.displayName).length * 10;
    }

    /**
     * @param {Row} row
     */
    isDisabled(row = null) {
        return this.model.useSampleModel;
    }

    /**
     * @param {Row} row
     */
    isHoverable(row) {
        return !this.model.useSampleModel;
    }

    /**
     * Folds each group into its predecessor while the predecessor is mergeable,
     * left to right. Written as a divide-and-conquer recursion before, which
     * allocated two arrays per level for a result a single pass produces --
     * both live `getAggregateValue` implementations (this one, and planning's
     * sum) fold in either order to the same value.
     *
     * @param {Group[]} groups
     * @returns {Group[]}
     */
    mergeGroups(groups) {
        if (groups.length <= 1) {
            return groups;
        }
        const merged = [groups[0]];
        for (const group of groups.slice(1)) {
            if (!group.break) {
                const previousGroup = merged.pop();
                group.break = previousGroup.break;
                group.grid.column[0] = previousGroup.grid.column[0];
                group.aggregateValue = this.getAggregateValue(group, previousGroup);
            }
            merged.push(group);
        }
        return merged;
    }

    onWillRender() {
        // A `model.notify()` used to reach here as a FORCED subtree render, which
        // fires `onWillUpdateProps` on children even when their props are
        // identical -- that is what re-ran `computeDerivedParams`. Now that the
        // render is reactive rather than forced, the rebuild is driven by the
        // model's own epoch, which is what `Model.updateEpoch` exists for.
        if (this.model.updateEpoch !== this._builtFromEpoch) {
            this.computeDerivedParams();
        }

        if (this.noDisplayedConnectors && this.shouldRenderConnectors()) {
            delete this.noDisplayedConnectors;
            this.computeDerivedParams();
        }

        if (this.shouldComputeSomeWidths) {
            this.computeSomeWidths();
        }

        if (this.shouldComputeSomeWidths || this.shouldComputeGridColumns) {
            this.computeVisibleColumns();
        }

        if (this.shouldComputeGridRows) {
            this.virtualGrid.setRowsHeights(this.gridRows);
            this.computeVisibleRows();
        }

        if (
            this.shouldComputeSomeWidths ||
            this.shouldComputeGridColumns ||
            this.shouldComputeGridRows
        ) {
            this.computeVisiblePills();
            if (this.shouldRenderConnectors()) {
                this.computeVisibleConnectors();
            } else {
                this.noDisplayedConnectors = true;
            }
        }

        delete this.shouldComputeSomeWidths;
        delete this.shouldComputeGridColumns;
        delete this.shouldComputeGridRows;
    }

    pushGridRows(gridRows) {
        for (const key of ["t0", "t1", "t2"]) {
            if (key in gridRows) {
                const types = new Array(gridRows[key]).fill(this.getRowTypeHeight(key));
                this.gridRows.push(...types);
            }
        }
    }

    processPillsAsRows(row, pills) {
        const rows = [];
        const parsedId = JSON.parse(row.id);
        if (pills.length) {
            for (const pill of pills) {
                const { id: resId, display_name: name } = pill.record;
                const subRow = {
                    id: JSON.stringify([...parsedId, { id: resId }]),
                    resId,
                    name,
                    groupLevel: row.groupLevel + 1,
                    recordIds: [resId],
                    fromServer: row.fromServer,
                    parentResId: row.resId ?? row.parentResId,
                    parentGroupedField: row.groupedByField || row.parentGroupedField,
                };
                rows.push(...this.processRow(subRow, false).rows);
            }
        } else {
            const subRow = {
                id: JSON.stringify([...parsedId, {}]),
                resId: false,
                name: "",
                groupLevel: row.groupLevel + 1,
                recordIds: [],
                fromServer: row.fromServer,
                parentResId: row.resId ?? row.parentResId,
                parentGroupedField: row.groupedByField || row.parentGroupedField,
            };
            rows.push(...this.processRow(subRow, false).rows);
        }

        return rows;
    }

    /**
     * @param {Row} row
     * @param {boolean} [processAsGroup=true]
     */
    groupPillsOf(recordIds) {
        const groupPills = [];
        for (const resId of recordIds) {
            const entry = this.prePillByRecordId.get(resId);
            if (entry) {
                groupPills.push(entry);
            }
        }
        groupPills.sort((a, b) => a.index - b.index);
        return groupPills.map((entry) => entry.pill);
    }

    layoutRowPills(row, groupPills, isGroup) {
        let rowPills = groupPills.map((pill) => ({ ...pill }));
        const gridRowTypes = isGroup ? { t0: 1 } : { t1: 1, t2: +!this.isTouchDevice };
        if (rowPills.length) {
            if (isGroup) {
                if (this.shouldComputeAggregateValues(row)) {
                    rowPills = this.aggregatePills(rowPills, row).map((group) =>
                        this.getPillFromGroup(group, row.consolidate),
                    );
                } else {
                    rowPills = [];
                }
            } else {
                gridRowTypes.t1 = this.calculatePillsLevel(rowPills);
            }
        }
        const progressBar = this.getRowProgressBar(row.groupedByField, row.resId);
        if (
            progressBar &&
            this.isTouchDevice &&
            (!gridRowTypes.t1 || gridRowTypes.t1 === 1)
        ) {
            // In mobile: rows span over 2 rows to alllow progressbars to properly display
            gridRowTypes.t1 = (gridRowTypes.t1 || 0) + 1;
        }
        return { rowPills, gridRowTypes, progressBar };
    }

    placeRowPills(rowId, rowPills) {
        for (const rowPill of rowPills) {
            rowPill.id = `__pill__${this.nextPillId++}`;
            const pillFirstRow = this.currentGridRow + rowPill.level;
            rowPill.grid = {
                ...rowPill.grid, // rowPill is a shallow copy of a prePill (possibly copied several times)
                row: [pillFirstRow, pillFirstRow + 1],
            };
            rowPill.rowId = rowId;
            this.pills[rowPill.id] = rowPill;
        }
        this.rowPills[rowId] = rowPills; // all row pills
    }

    rowThumbnailUrl(groupedByField, resId) {
        const field = this.model.metaData.thumbnails[groupedByField];
        if (!field) {
            return undefined;
        }
        const model = this.model.metaData.fields[groupedByField].relation;
        return url("/web/image", { model, id: resId, field });
    }

    processRow(row, processAsGroup = true) {
        const { displayUnavailability } = this.model.metaData;
        const { displayMode } = this.model.displayParams;
        const {
            fromServer,
            groupedByField,
            groupLevel,
            id,
            name,
            parentResId,
            parentGroupedField,
            resId,
            rows,
            recordIds,
            __extra__,
        } = row;

        const groupPills = this.groupPillsOf(recordIds);
        if (displayMode === "sparse" && __extra__) {
            return { rows: this.processPillsAsRows(row, groupPills) };
        }

        const isGroup = displayMode === "sparse" ? processAsGroup : Boolean(rows);
        const { rowPills, gridRowTypes, progressBar } = this.layoutRowPills(
            row,
            groupPills,
            isGroup,
        );
        if (row.id !== "[]") {
            this.pushGridRows(gridRowTypes);
        }
        const subRowsCount = Object.values(gridRowTypes).reduce(
            (acc, val) => acc + val,
            0,
        );
        const gridRow = [this.currentGridRow, this.currentGridRow + subRowsCount];
        this.placeRowPills(id, rowPills);

        /** @type {Row} */
        const processedRow = {
            cellColors: {},
            fromServer,
            groupedByField,
            groupLevel,
            id,
            isGroup,
            name,
            progressBar,
            resId,
            grid: { row: gridRow },
            thumbnailUrl: this.rowThumbnailUrl(groupedByField, resId),
        };
        if (displayUnavailability && !isGroup) {
            processedRow.unavailabilities = this.getRowUnavailabilities(
                parentGroupedField || groupedByField,
                parentResId ?? resId,
            );
        }
        processedRow.avatar = this.getRowAvatar(processedRow);
        this.rowByIds[id] = processedRow;
        this.currentGridRow += subRowsCount;

        const result = { rows: [processedRow] };
        if (!this.model.isClosed(id)) {
            if (rows) {
                for (const subRow of rows) {
                    result.rows.push(...this.processRow(subRow).rows);
                }
            } else if (displayMode === "sparse" && processAsGroup) {
                result.rows.push(...this.processPillsAsRows(row, groupPills));
            }
        }
        return result;
    }

    /**
     * @returns {boolean}: whether one of the "groupedBy" fields of the model is readonly
     */
    containsReadonlyGroup() {
        return this.model.metaData.groupedBy.some(
            (groupedByField) => this.model.metaData.fields[groupedByField].readonly,
        );
    }

    /**
     * For all rows to render, specify whether the row is grouped by a readonly
     * field or is a child of a row grouped by a readonly field - by setting its'
     * 'readonly' and 'readonlyChild' properties.
     */
    setupInitialReadonly() {
        let foundReadonlyField = false;
        const readonlyGroups = [];
        const readonlyChildren = [];
        for (const groupedByField of this.props.model.metaData.groupedBy) {
            // Field itself is readonly
            if (this.model.metaData.fields[groupedByField].readonly) {
                foundReadonlyField = true;
                readonlyGroups.push(groupedByField);
            }
            // There is a readonly parent group
            else if (foundReadonlyField) {
                readonlyChildren.push(groupedByField);
            }
        }

        for (const row of this.rows) {
            row.readonlyChild = readonlyChildren.includes(row.groupedByField);
            row.readonly =
                readonlyGroups.includes(row.groupedByField) || row.readonlyChild;
        }
    }

    /**
     * @param {Row} row
     */
    shouldComputeAggregateValues(row) {
        return true;
    }

    shouldMergeGroups() {
        return true;
    }

    computeUnavailabilityPeriods() {
        const { cellPart, unit } = this.model.metaData.scale;
        const columns = [...Array(this.columnCount).keys()].map((i) =>
            this.getColumnFromColNumber(i * cellPart + 1),
        );
        ({
            foldableColumns: this.foldableColumns,
            foldableColumnsMapping: this.foldableColumnsMapping,
        } = computeFoldableColumns({
            columns,
            rows: this.rows,
            pills: Object.values(this.pills),
            cellPart,
            unit,
        }));
    }

    computeFoldedGrid() {
        this.shouldComputeSomeWidths = true;
        const { cellPart, unit } = this.model.metaData.scale;
        const folded = computeFoldedGrid({
            foldableColumns: this.foldableColumns,
            previousFoldedColumns: this.offHoursState.foldedColumns,
            columnCount: this.columnCount,
            cellPart,
            unit,
        });
        if (!folded) {
            clearObject(this.offHoursState);
            return;
        }
        Object.assign(this.offHoursState, folded);
    }

    toggleFoldableColumn(column, fold) {
        if (!this.offHoursState.foldedColumns) {
            this.offHoursState.foldedColumns = new Array(this.columnCount).fill(0);
        }
        const { startIndex, stopIndex } = this.foldableColumnsMapping[column.index];
        this.offHoursState.foldedColumns.fill(fold ? 1 : 0, startIndex, stopIndex + 1);
        this.computeFoldedGrid();
        this.cleanMultiSelection();
    }

    toggleCollapsableColumnHeaderHighlighting(collapsableColumnHeader) {
        if (
            !collapsableColumnHeader ||
            collapsableColumnHeader.classList.contains("o_gantt_header_folded")
        ) {
            const columnHeaders = this.gridRef.el.querySelectorAll(
                ".o_gantt_foldable_hovered",
            );
            for (const columnHeader of columnHeaders) {
                columnHeader.classList.remove("o_gantt_foldable_hovered");
            }
            return;
        }
        const columnHeaders = this.gridRef.el.querySelectorAll(".o_gantt_foldable");
        const foldableColumnsGroup =
            this.foldableColumnsMapping[+collapsableColumnHeader.dataset.columnIndex];
        for (const columnHeader of columnHeaders) {
            const columnIndex = +columnHeader.dataset.columnIndex;
            const currentGroup = this.foldableColumnsMapping[columnIndex];
            if (
                foldableColumnsGroup.foldableGroupNum === currentGroup.foldableGroupNum
            ) {
                columnHeader.classList.add("o_gantt_foldable_hovered");
            } else {
                columnHeader.classList.remove("o_gantt_foldable_hovered");
            }
        }
    }

    normalizeTimeRange(start, stop) {
        stop = stop.add({ seconds: 1 });
        return { start, stop };
    }
}
