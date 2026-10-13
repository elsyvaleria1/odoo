/** @odoo-module native */
import {
    Component,
    markup,
    onMounted,
    onPatched,
    onWillUpdateProps,
    proxy,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { useVirtualGrid } from "@web/core/utils/virtual_grid";
import { useViewConfig } from "@web/core/view_config_hooks";
import { Field } from "@web/fields/field";
import { useReactiveModel } from "@web/model/model";
import { ViewScaleSelector } from "@web/views/view_components";
import { GridComponent } from "@web_grid/components/grid_component/grid_component";
import { setCellReadonlyHidden } from "@web_grid/hooks/grid_cell_hook";

export class GridRenderer extends Component {
    static components = {
        Field,
        GridComponent,
        ViewScaleSelector,
    };

    static template = "web_grid.Renderer";

    static props = {
        sections: t.array().optional([]),
        columns: t.array().optional([]),
        rows: t.array().optional([]),
        model: t.object().optional({}),
        options: t.object(),
        sectionField: t.object().optional(),
        rowFields: t.array(),
        measureField: t.object(),
        isEditable: t.boolean(),
        widgetPerFieldName: t.object(),
        openAction: t.object().optional(),
        contentRef: t.function(),
        createInline: t.boolean(),
        createRecord: t.function(),
        ranges: t.object().optional({}),
        state: t.object(),
        isWeekendVisible: t.boolean(),
        toggleWeekendVisibility: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.config = useViewConfig();
        this.ui = useService("ui");
        this.model = useReactiveModel(this.props.model);
        this.rendererRef = elementRef();
        this.actionService = useService("action");
        this.editionState = proxy({
            hoveredCellInfo: false,
            editedCellInfo: false,
        });
        this.hoveredElement = null;
        const measureFieldName = this.model.measureFieldName;
        const widgetName =
            this.props.widgetPerFieldName[measureFieldName] ||
            this.model.fieldsInfo[measureFieldName].type;
        this.gridCell = registry.category("grid_components").get(widgetName);
        this.hoveredCellProps = this._makeMeasureCellProps(widgetName, false);
        this.editCellProps = this._makeMeasureCellProps(widgetName, true);
        onWillUpdateProps(this.onWillUpdateProps);
        onMounted(this._focusOnToday);
        onPatched(this._focusOnToday);
        this.shouldFocusOnToday = true;
        this.onMouseOver = useDebounced(this._onMouseOver.bind(this), 10);
        this.onMouseOut = useDebounced(this._onMouseOut.bind(this), 10);
        this.virtualGrid = useVirtualGrid({
            scrollableRef: this.props.contentRef,
            initialScroll: { top: 60 },
        });
        useListener(window, "click", this.onClick.bind(this));
        useListener(window, "keydown", this.onKeyDown.bind(this));
    }

    /**
     * @private
     * @param {string} widgetName
     * @param {boolean} editMode
     * @return {Object}
     */
    _makeMeasureCellProps(widgetName, editMode) {
        const measureFieldName = this.model.measureFieldName;
        return {
            name: measureFieldName,
            type: widgetName,
            component: this.gridCell.component,
            reactive: proxy({ cell: null }),
            fieldInfo: this.model.fieldsInfo[measureFieldName],
            readonly: !this.props.isEditable,
            openRecords: this.openRecords.bind(this),
            editMode,
            onEdit: this.onEditCell.bind(this),
            getCell: this.getCell.bind(this),
            isMeasure: true,
            ...(editMode ? { onKeyDown: this.onCellKeydown.bind(this) } : {}),
        };
    }

    getCell(rowId, columnId) {
        return this.model.data.rows[rowId]?.cells[columnId];
    }

    getItemHeight(item) {
        let height = this.rowHeight;
        if (item.isSection && item.isFake) {
            return 0;
        }
        if (!item.isSection && this.displayAddLine(item)) {
            height *= 2;
        }
        return height;
    }

    get isMobile() {
        return this.ui.isSmall;
    }

    get rowHeight() {
        const baseHeight = this.isMobile ? 48 : 32;
        const extraHeight = this.isMobile
            ? Math.max(0, this.model.rowFields.length - 2) * 20
            : 0;
        return baseHeight + extraHeight;
    }

    /** @return {Array} */
    get virtualRows() {
        this.virtualGrid.setRowsHeights(
            this.props.rows.map((row) => this.getItemHeight(row)),
        );
        const [start, end] = this.virtualGrid.rowsIndexes;
        return this.props.rows.slice(start, end + 1);
    }

    /** @return {number} */
    get columnsGrandTotal() {
        return this.props.columns.reduce((total, c) => total + c.grandTotal, 0);
    }

    /** @return {Map<number, number>} */
    get rowIndexes() {
        if (this._rowIndexesOf !== this.props.rows) {
            this._rowIndexesOf = this.props.rows;
            this._rowIndexes = new Map(this.props.rows.map((r, i) => [r.id, i]));
        }
        return this._rowIndexes;
    }

    /** @return {Map<number, number>} */
    get sectionIndexes() {
        if (this._sectionIndexesOf !== this.props.sections) {
            this._sectionIndexesOf = this.props.sections;
            this._sectionIndexes = new Map(
                this.props.sections.map((s, i) => [s.id, i]),
            );
        }
        return this._sectionIndexes;
    }

    /**
     * @param {import("./grid_model").GridSection} section
     * @return {boolean}
     */
    isSectionDisplayed(section) {
        return Boolean(
            section &&
            !section.isFake &&
            (section.value || this.props.sections.length > 1),
        );
    }

    /** @return {number} */
    get displayedSectionsCount() {
        return this.props.sections.filter((s) => this.isSectionDisplayed(s)).length;
    }

    getRowPosition(row, isCreateInlineRow = false) {
        const rowIndex = row ? (this.rowIndexes.get(row.id) ?? -1) : 0;
        const section = row && row.getSection();
        const sectionDisplayed = this.isSectionDisplayed(section);
        let rowPosition =
            this.rowsGap +
            rowIndex +
            1 +
            (sectionDisplayed ? (this.sectionIndexes.get(section.id) ?? 0) : 0);
        if (isCreateInlineRow) {
            rowPosition += 1;
        }
        if (!sectionDisplayed) {
            rowPosition -= 1;
        }
        return rowPosition;
    }

    getTotalRowPosition() {
        return (
            (this.props.rows.length || 1) +
            this.displayedSectionsCount +
            (this.props.createInline ? 1 : 0) +
            this.rowsGap
        );
    }

    onWillUpdateProps(nextProps) {}

    /**
     * @param {number} value
     * @return {string}
     */
    formatValue(value) {
        return this.gridCell.formatter(value, {
            digits: this.model.fieldsInfo[this.model.measureFieldName]?.digits,
        });
    }

    /** @return {number} */
    get rowsCount() {
        const addLineRows = this.props.createInline
            ? this.props.sections.length || 1
            : 0;
        const dataRows = this.props.rows.length - this.props.sections.length;
        return dataRows + this.displayedSectionsCount + addLineRows;
    }

    get gridTemplateRows() {
        let totalRows = 0;
        if (!this.props.options.hideColumnTotal) {
            totalRows += 1;
            if (this.props.options.hasBarChartTotal) {
                totalRows += 1;
            }
        }
        return `auto repeat(${this.rowsCount + totalRows}, ${this.rowHeight}px)`;
    }

    /**
     * @return {string}
     */
    get gridTemplateColumns() {
        const cellWidth =
            this.props.columns.length > 7
                ? "minmax(var(--o-grid-cell-minwidth-dense), auto)"
                : "minmax(var(--o-grid-cell-minwidth), 1fr)";
        return (
            `auto repeat(${this.props.columns.length}, ${cellWidth}) ` +
            "minmax(var(--o-grid-cell-minwidth), var(--o-grid-total-column-width))"
        );
    }

    get measureLabel() {
        const measureFieldName = this.model.measureFieldName;
        if (measureFieldName === "__count") {
            return _t("Total");
        }
        return this.props.measureField.string;
    }

    get rowsGap() {
        return 1;
    }

    get columnsGap() {
        return 1;
    }

    /**
     * @param {import("./grid_model").GridRow} row
     * @return {boolean}
     */
    displayAddLine(row) {
        return this.props.createInline && row.section.lastRow.id === row.id;
    }

    getCellColorClass(column, section) {
        return "text-900";
    }

    getSectionColumnsClasses(column, row) {
        const isToday = column.isToday;
        return {
            "bg-info bg-opacity-50": isToday,
            "bg-200 border-top": !isToday,
            "bg-opacity-75":
                this.getUnavailableClass(column) === "o_grid_unavailable" &&
                row.cells[column.id].value === 0,
        };
    }

    getSectionCellsClasses(column, row) {
        return {
            "text-opacity-25":
                row.cells[column.id].value === 0 ||
                this.getUnavailableClass(column) === "o_grid_unavailable",
        };
    }

    isTextDanger() {
        return false;
    }

    getTextColorClasses(column, row, isEven) {
        const value = row.cells[column.id].value;
        const isTextDanger = this.isTextDanger(row, column);
        return {
            "text-bg-view": isEven && value >= 0 && !isTextDanger,
            "text-900": !isEven && value >= 0 && !isTextDanger,
            "text-danger": value < 0 || isTextDanger,
        };
    }

    getCellsClasses(column, row, isEven) {
        return {
            ...this.getTextColorClasses(column, row, isEven),
            o_grid_cell_today: column.isToday,
            "fst-italic": row.isAdditionalRow,
        };
    }

    /**
     * @param {GridSection | GridRow} section
     */
    _getTotalCellBgColor(section) {
        return "text-bg-800";
    }

    getSectionTotalRowClass(section, grandTotal) {
        return {
            [this._getTotalCellBgColor(section)]: true,
            "text-opacity-25": grandTotal === 0,
        };
    }

    getColumnBarChartHeightStyle(column) {
        let heightPercentage = 0;
        if (this.model.maxColumnsTotal !== 0) {
            heightPercentage = (column.grandTotal / this.model.maxColumnsTotal) * 100;
        }
        return `height: ${heightPercentage}%; bottom: 0;`;
    }

    getFooterTotalCellClasses(grandTotal) {
        if (grandTotal < 0) {
            return "bg-danger text-bg-danger";
        }

        return "bg-400";
    }

    /**
     * @param {import("./grid_model").GridColumn} column
     * @param {{row?: Object, section?: Object}} cellData
     * @return {string}
     */
    getUnavailableClass(column, cellData = {}) {
        return "";
    }

    getFieldAdditionalProps(fieldName) {
        return {
            name: fieldName,
            type:
                this.props.widgetPerFieldName[fieldName] ||
                this.model.fieldsInfo[fieldName].type,
        };
    }

    getCellsTextClasses(column, row) {
        return {
            "text-900 text-opacity-25": row.cells[column.id].value === 0,
        };
    }

    getTotalCellsTextClasses(row, grandTotal) {
        return {
            "fst-italic": row.isAdditionalRow,
            "text-bg-200": grandTotal >= 0,
            "bg-danger text-bg-danger": grandTotal < 0,
            "text-opacity-50": grandTotal === 0,
        };
    }

    onCreateInlineClick(section) {
        const context = {
            ...section?.context,
        };
        const title = _t("Add a Line");
        this.props.createRecord({ context, title });
    }

    _focusOnToday() {
        if (!this.shouldFocusOnToday) {
            return;
        }
        this.shouldFocusOnToday = false;
        const { navigationInfo, columnFieldIsDate } = this.model;
        if (
            this.isMobile ||
            !columnFieldIsDate ||
            navigationInfo.range.name !== "month"
        ) {
            return;
        }
        const rendererEl = this.rendererRef.el;
        const todayEl = rendererEl.querySelector("div.o_grid_column_title.fw-bolder");
        if (todayEl) {
            rendererEl.parentElement.scrollLeft =
                todayEl.offsetLeft -
                rendererEl.offsetWidth / 2 +
                todayEl.offsetWidth / 2;
        }
    }

    _onMouseOver(ev) {
        if (
            this.hoveredElement ||
            ev.relatedTarget?.classList?.contains("dropdown-item")
        ) {
            return;
        }
        const highlightableElement = ev.target.closest(".o_grid_highlightable");
        if (!highlightableElement) {
            return;
        }
        const { column, gridRow, gridColumn, row } = highlightableElement.dataset;
        const rowMates = this.rendererRef.el.querySelectorAll(
            `.o_grid_highlightable[data-grid-row="${gridRow}"]:not(.o_grid_add_line):not(.o_grid_column_title)`,
        );
        for (const node of rowMates) {
            node.classList.add("o_grid_highlighted");
            node.classList.add(
                node.dataset.gridColumn === gridColumn
                    ? "o_grid_cell_highlighted"
                    : "o_grid_row_highlighted",
            );
        }
        this.rendererRef.el
            .querySelector(
                `.o_grid_bar_chart_container[data-grid-column="${gridColumn}"]`,
            )
            ?.classList.add("o_grid_highlighted");
        this.hoveredElement = highlightableElement;
        const cell = this.editCellProps.reactive.cell;
        if (
            row &&
            column &&
            !(cell && cell.dataset.row === row && cell.dataset.column === column)
        ) {
            this.hoveredCellProps.reactive.cell = highlightableElement;
        }
    }

    /** @param {MouseEvent} ev */
    _onMouseOut(ev) {
        if (!this.hoveredElement) {
            return;
        }
        /** @type {HTMLElement | null} */
        let relatedTarget = ev.relatedTarget;
        const gridCell = relatedTarget?.closest(".o_grid_cell");
        if (
            gridCell &&
            gridCell.dataset.gridRow === this.hoveredElement.dataset.gridRow &&
            gridCell.dataset.gridColumn === this.hoveredElement.dataset.gridColumn &&
            gridCell !== this.editCellProps.reactive.cell
        ) {
            return;
        }
        while (relatedTarget) {
            if (relatedTarget === this.hoveredElement) {
                return;
            }
            relatedTarget = relatedTarget.parentElement;
        }
        const { gridRow, gridColumn } = this.hoveredElement.dataset;
        const elementsHighlighted = this.rendererRef.el.querySelectorAll(
            `.o_grid_highlightable[data-grid-row="${gridRow}"], .o_grid_highlightable[data-grid-column="${gridColumn}"]`,
        );
        for (const node of elementsHighlighted) {
            node.classList.remove(
                "o_grid_highlighted",
                "o_grid_row_highlighted",
                "o_grid_cell_highlighted",
            );
        }
        this.hoveredElement = null;
        if (this.hoveredCellProps.reactive.cell) {
            setCellReadonlyHidden(this.hoveredCellProps.reactive.cell, false);
            this.hoveredCellProps.reactive.cell = null;
        }
    }

    onEditCell(value) {
        if (this.editCellProps.reactive.cell) {
            setCellReadonlyHidden(this.editCellProps.reactive.cell, false);
        }
        if (value) {
            this.editCellProps.reactive.cell = this.hoveredCellProps.reactive.cell;
            this.hoveredCellProps.reactive.cell = null;
        } else {
            this.editCellProps.reactive.cell = null;
        }
    }

    _onKeyDown(ev) {
        const hotkey = getActiveHotkey(ev);
        if (hotkey === "escape" && this.editCellProps.reactive.cell) {
            this.onEditCell(false);
        }
    }

    /** @param {KeyboardEvent} ev */
    onKeyDown(ev) {
        this._onKeyDown(ev);
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        if (
            !this.editCellProps.reactive.cell ||
            ev.target.closest(".o_grid_highlighted") ||
            ev.target.closest(".o_grid_cell")
        ) {
            return;
        }
        this.onEditCell(false);
    }

    /** @param {MouseEvent} ev */
    onCellClick(ev) {
        ev.stopPropagation();
        const cell = ev.target.closest(".o_grid_highlightable");
        const { row, column } = cell.dataset;
        if (row && column) {
            if (this.editCellProps.reactive.cell) {
                setCellReadonlyHidden(this.editCellProps.reactive.cell, false);
            }
            this.editCellProps.reactive.cell = cell;
        }
    }

    /**
     * @param {KeyboardEvent} ev
     * @param {import("./grid_model").GridCell | null} cell
     */
    onCellKeydown(ev, cell) {
        const hotkey = getActiveHotkey(ev);
        if (
            !this.rendererRef.el ||
            !cell ||
            !["tab", "shift+tab", "enter"].includes(hotkey)
        ) {
            this._onKeyDown(ev);
            return;
        }
        ev.preventDefault();
        ev.stopImmediatePropagation();
        let rowId = cell.row.id;
        let columnId = cell.column.id;
        const columnIds = this.props.columns.map((c) => c.id);
        const rowIds = [];
        for (const item of this.props.rows) {
            if (!item.isSection) {
                rowIds.push(item.id);
            }
        }
        let columnIndex = columnIds.indexOf(columnId);
        let rowIndex = rowIds.indexOf(rowId);
        if (hotkey === "tab") {
            columnIndex += 1;
            rowIndex += 1;
            if (columnIndex < columnIds.length) {
                columnId = columnIds[columnIndex];
            } else {
                columnId = columnIds[0];
                if (rowIndex < rowIds.length) {
                    rowId = rowIds[rowIndex];
                } else {
                    rowId = rowIds[0];
                }
            }
        } else if (hotkey === "shift+tab") {
            columnIndex -= 1;
            rowIndex -= 1;
            if (columnIndex >= 0) {
                columnId = columnIds[columnIndex];
            } else {
                columnId = columnIds[columnIds.length - 1];
                if (rowIndex >= 0) {
                    rowId = rowIds[rowIndex];
                } else {
                    rowId = rowIds[rowIds.length - 1];
                }
            }
        } else if (hotkey === "enter") {
            rowIndex += 1;
            if (rowIndex >= rowIds.length) {
                columnIndex = (columnIndex + 1) % columnIds.length;
                columnId = columnIds[columnIndex];
            }
            rowIndex = rowIndex % rowIds.length;
            rowId = rowIds[rowIndex];
        }
        this.onEditCell(false);
        this._focusGridCell(rowId, columnId);
    }

    /**
     * @param {number|string} rowId
     * @param {number|string} columnId
     */
    _focusGridCell(rowId, columnId) {
        const selector = `.o_grid_highlightable[data-row="${rowId}"][data-column="${columnId}"]`;
        const cellEl = this.rendererRef.el.querySelector(selector);
        if (cellEl) {
            this.hoveredCellProps.reactive.cell = cellEl;
            this.onEditCell(true);
            return;
        }
        const rowIndex = this.rowIndexes.get(rowId) ?? -1;
        if (rowIndex !== -1 && this.props.contentRef.el) {
            let offset = 0;
            for (let i = 0; i < rowIndex; i++) {
                offset += this.getItemHeight(this.props.rows[i]);
            }
            this.props.contentRef.el.scrollTop = offset;
        }
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                this.hoveredCellProps.reactive.cell =
                    this.rendererRef.el.querySelector(selector);
                this.onEditCell(true);
            });
        });
    }

    async openRecords(actionTitle, domain, context) {
        const resModel = this.model.resModel;
        if (this.props.openAction) {
            const resIds = await this.model.orm.search(resModel, domain);
            this.actionService.doActionButton({
                ...this.props.openAction,
                resModel,
                resIds,
                context,
            });
        } else {
            const { views = [] } = this.config;
            const openRecordsViews = ["list", "form"].map((viewType) => {
                const view = views.find((view) => view[1] === viewType);
                return [view ? view[0] : false, viewType];
            });
            this.actionService.doAction({
                type: "ir.actions.act_window",
                name: actionTitle,
                res_model: resModel,
                views: openRecordsViews,
                domain,
                context,
                help: this._getNoContentHelper(),
            });
        }
    }

    _getNoContentHelper() {
        const noRecordsFound = _t("No records found");
        return markup`<p class='o_view_nocontent_smiling_face'>${noRecordsFound}</p>`;
    }

    get rangesArray() {
        return Object.values(this.props.ranges);
    }

    async onRangeClick(name) {
        await this.model.setRange(name);
        this.props.state.activeRangeName = name;
        this.shouldFocusOnToday = true;
    }

    async onTodayButtonClick() {
        await this.model.setTodayAnchor();
        this.shouldFocusOnToday = true;
    }

    async onPreviousButtonClick() {
        await this.model.moveAnchor("backward");
        this.shouldFocusOnToday = true;
    }

    async onNextButtonClick() {
        await this.model.moveAnchor("forward");
        this.shouldFocusOnToday = true;
    }
}
