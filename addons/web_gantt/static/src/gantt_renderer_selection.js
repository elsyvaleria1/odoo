/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { useCallbackRecorder } from "@web/core/action_hook";
import { useBus } from "@web/core/utils/hooks";
import { useGanttContext } from "@web_gantt/gantt_context";

import { getBadges, useGanttSelectable } from "./gantt_helpers.js";
import { firstSelectedRun, parseCellKey } from "./gantt_layout.js";
import { rtl } from "./gantt_renderer_core.js";
import { GanttRendererDialogs } from "./gantt_renderer_dialogs.js";

export class GanttRendererSelection extends GanttRendererDialogs {
    setup() {
        super.setup();
        this.ganttContext = useGanttContext();
        this.prepareSelectionFeature();
    }

    appendCellGhost({ startCol, endCol, startRow, endRow }) {
        this.cellGhost.style = this.getGridPosition({
            row: [startRow, endRow],
            column: [startCol, endCol],
        });
        this.addStickyCoordinates([startRow, endRow], [startCol, endCol]);
        this.cellContainerRef.el.append(this.cellGhost);
    }

    drawCellGhosts(selectedCells) {
        this.removeCellGhosts();
        const rows = [];
        const columns = [];
        for (const selectedCell of selectedCells) {
            const clone = this.cellGhost.cloneNode();
            const { startRow, endRow, startCol, endCol } = this.getBlock(selectedCell);
            const row = [startRow, endRow];
            const column = [startCol, endCol];
            clone.style = this.getGridPosition({ row, column });
            this.cellContainerRef.el.append(clone);
            rows.push(...row);
            columns.push(...column);
        }
        this.addStickyCoordinates(rows, columns);
    }

    removeCellGhosts() {
        for (const ghost of this.gridRef.el.querySelectorAll(".o_cell_ghost")) {
            ghost.remove();
        }
        this.removeStickyCoordinates();
    }

    removeCellGhost() {
        this.cellGhost.remove();
        this.removeStickyCoordinates();
    }

    getAllCells(cells, action) {
        switch (action) {
            case "add":
                return this.selectedCells.union(cells);
            case "toggle":
                return this.selectedCells.symmetricDifference(cells);
            case "replace":
                return cells;
        }
    }

    updateMultiSelection({ startCol, endCol, startRow, endRow }, action) {
        const cells = this.getCellsInBlock({ startCol, endCol, startRow, endRow });
        this.selectedCells = this.getAllCells(cells, action);
        this.multiSelectionButtonsReactive.visible = Boolean(this.selectedCells.size);
        this.multiSelectionButtonsReactive.nbSelected = this.getSelectedRecordIds(
            this.selectedCells,
        ).length;
        if (this.selectedCells.size === 1 && this.model.metaData.canPlan) {
            const selectedCell = [...this.selectedCells][0];
            const { startRow, startCol } = this.getBlock(selectedCell);
            const rowId = this.rowIdsByFirstRow[startRow];
            this.multiSelectionButtonsReactive.onPlan = () =>
                this.onPlan(rowId, startCol, startCol);
        } else {
            delete this.multiSelectionButtonsReactive.onPlan;
        }
    }

    createFromSelection() {
        if (!this.selectedCells?.size) {
            return false;
        }
        const firstBlock = firstSelectedRun(
            [...this.selectedCells].map((cell) => parseCellKey(cell)),
        );
        const rowId = this.rowIdsByFirstRow[firstBlock.startRow];
        this.onCreate(rowId, firstBlock.startCol, firstBlock.endCol - 1);
        return true;
    }

    cleanMultiSelection() {
        this.selectedCells = new Set();
        this.multiSelectionButtonsReactive.visible = false;
        this.multiSelectionButtonsReactive.nbSelected = 0;
        delete this.multiSelectionButtonsReactive.onPlan;
        this.removeCellGhosts();
    }

    prepareMultiSelectionButtonsReactive() {
        return proxy({
            onCancel: this.cleanMultiSelection.bind(this),
            onAdd: (multiCreateData) => {
                this.onMultiCreate(multiCreateData, this.selectedCells);
                this.cleanMultiSelection();
            },
            onDelete: () => {
                this.onMultiDelete(this.selectedCells);
                this.cleanMultiSelection();
            },
            nbSelected: 0,
            resModel: this.model.metaData.resModel,
            multiCreateView: this.model.metaData.multiCreateView || "",
            multiCreateValues: this.props.multiCreateValues,
            showMultiCreateTimeRange: this.model.showMultiCreateTimeRange,
            visible: false,
            context: this.model.searchParams.context,
        });
    }

    prepareSelectionFeature() {
        this.selectedCells = new Set();
        this.selectionAction = null;
        // Whether "dragend" should clean the current selection up: not after a
        // multi-select "drop", where the selection is what was just made.
        this.cleanupSelectionOnDragEnd = true;
        this.cellGhost = document.createElement("div");
        this.cellGhost.classList.add(
            "o_gantt_cell",
            "o_drag_hover",
            "o_cell_ghost",
            "pe-none",
        );
        this.multiSelectionButtonsReactive =
            this.prepareMultiSelectionButtonsReactive();
        // One stable object, so the controls' props stay shallow-equal from one
        // renderer render to the next and the toolbar is not re-rendered on scroll.
        this.controlsCallbacks.multiSelection = {
            Component: this.constructor.components.MultiSelectionButtons,
            reactive: this.multiSelectionButtonsReactive,
        };

        const selectState = useGanttSelectable(this.cellSelectOptions());
        if (this.model.hasMultiCreate) {
            this.dragStates.push(useGanttSelectable(this.pillSelectOptions()));
        }

        useBus(this.model.bus, "update", this.cleanMultiSelection.bind(this));

        useCallbackRecorder(
            this.ganttContext.createFromSelectionCallBackRecorder,
            this.createFromSelection.bind(this),
        );

        this.dragStates.push(selectState);
    }

    updateSelectionGhost({ startCol, endCol, startRow, endRow }) {
        if (this.model.hasMultiCreate) {
            const cells = this.getCellsInBlock({ startCol, endCol, startRow, endRow });
            this.drawCellGhosts(this.getAllCells(cells, this.selectionAction));
            return;
        }
        this.appendCellGhost({ startCol, endCol, startRow, endRow });
        const getDatetime = (col) => this.getSubColumnFromColNumber(col).start;
        this.updateBadges(
            getBadges(this.cellGhost, [getDatetime(startCol)], [getDatetime(endCol)], {
                rtl: rtl(),
                scale: this.model.metaData.scale,
            }),
        );
    }

    startSelection(block) {
        this.selectionAction = this.ctrlPressed ? "add" : "replace";
        this.updateSelectionGhost(block);
    }

    cellSelectOptions() {
        return {
            enable: () =>
                Boolean(this.cellForDrag.el) &&
                !this.cellForDrag.el.classList.contains("o_gantt_group") &&
                (this.model.metaData.canCellCreate || this.model.hasMultiCreate),
            ref: this.gridRef,
            hoveredCell: this.cellForDrag,
            elements: ".o_gantt_cells",
            ignore: ".o_gantt_pill_wrapper,.o_gantt_connector",
            edgeScrolling: {
                speed: 40,
                threshold: 150,
                direction: this.model.hasMultiCreate ? undefined : "horizontal",
            },
            hasMultiCreate: () => this.model.hasMultiCreate,
            rtl,
            scale: () => this.model.metaData.scale,
            onDragStart: (block) => this.startSelection(block),
            onDrag: (block) => this.updateSelectionGhost(block),
            onDrop: ({ rowId, startCol, endCol, startRow, endRow }) => {
                if (this.model.hasMultiCreate) {
                    this.updateMultiSelection(
                        { startCol, endCol, startRow, endRow },
                        this.selectionAction,
                    );
                    this.cleanupSelectionOnDragEnd = false;
                } else {
                    this.onCreate(rowId, startCol, endCol - 1);
                }
                this.selectionAction = null;
            },
            onDragEnd: () => {
                if (!this.cleanupSelectionOnDragEnd) {
                    this.cleanupSelectionOnDragEnd = true;
                    return;
                }
                if (this.model.hasMultiCreate) {
                    this.removeCellGhosts();
                    this.cleanMultiSelection();
                } else {
                    this.removeCellGhost();
                }
                this.clearBadges();
            },
        };
    }

    pillSelectOptions() {
        return {
            enable: () =>
                Boolean(this.cellForDrag.el) &&
                !this.cellForDrag.el.classList.contains("o_gantt_group"),
            ref: this.gridRef,
            hoveredCell: this.cellForDrag,
            elements: ".o_undraggable",
            edgeScrolling: { speed: 40, threshold: 150, direction: undefined },
            hasMultiCreate: () => true,
            rtl,
            scale: () => this.model.metaData.scale,
            onDragStart: (block) => this.startSelection(block),
            onDrag: (block) => this.updateSelectionGhost(block),
            onDrop: ({ startCol, endCol, startRow, endRow }) => {
                this.updateMultiSelection(
                    { startCol, endCol, startRow, endRow },
                    this.selectionAction,
                );
                this.selectionAction = null;
            },
        };
    }

    /**
     * Which records each grid cell holds and which record row starts at each
     * grid row, for the multi-selection: `getSelectedRecordIds` and
     * `getCellsInfo` read them, and so does hr_work_entry_enterprise.
     */
    indexPillsForMultiCreate() {
        /** @type {Record<string, Record<string, any>[]>} */
        this.mappingCellToRecords = {};
        /** @type {Record<number, RowId>} */
        this.rowIdsByFirstRow = {};
        if (!this.model.hasMultiCreate) {
            return;
        }
        for (const row of this.rows) {
            if (!row.isGroup) {
                this.rowIdsByFirstRow[row.grid.row[0]] = row.id;
            }
        }
        for (const pill of Object.values(this.pills)) {
            const row = this.rowByIds[pill.rowId];
            if (row.isGroup) {
                continue;
            }
            const subKey = `${row.grid.row[0]}_${row.grid.row[1]}`;
            const [firstCol, lastCol] = pill.grid.column;
            for (let col = firstCol; col < lastCol; col++) {
                const key = `${subKey}_${col}_${col + 1}`;
                this.mappingCellToRecords[key] ??= [];
                this.mappingCellToRecords[key].push(pill.record);
            }
        }
    }

    getSelectedRecordIds(selectedCells, predicate = () => true) {
        const ids = new Set();
        for (const selectedCell of selectedCells) {
            const recordsInSelectedCell = this.mappingCellToRecords[selectedCell];
            for (const record of recordsInSelectedCell || []) {
                if (predicate(record)) {
                    ids.add(record.id);
                }
            }
        }
        return [...ids];
    }

    onMultiDelete(selectedCells) {
        const ids = this.getSelectedRecordIds(selectedCells);
        return this.model.unlinkRecords(ids);
    }

    getCellsInBlock(block) {
        const { startCol, endCol, startRow, endRow } = block;
        const gridRowByFirstRow = {};
        for (const row of this.rows) {
            const gridRow = row.grid.row;
            const [first] = gridRow;
            if (first >= endRow) {
                break;
            }
            if (startRow <= first && !row.isGroup) {
                gridRowByFirstRow[first] = gridRow;
            }
        }
        const notFoldedCols = new Set();
        for (let col = startCol; col < endCol; col++) {
            const columnIndex = this.getColumnIndexFromColNumber(col);
            const isFolded = Boolean(this.offHoursState.foldedColumns?.[columnIndex]);
            if (!isFolded) {
                notFoldedCols.add(col);
            }
        }
        const cells = new Set();
        for (const gridRow of Object.values(gridRowByFirstRow)) {
            const subKey = `${gridRow[0]}_${gridRow[1]}`;
            for (const col of notFoldedCols) {
                cells.add(`${subKey}_${col}_${col + 1}`);
            }
        }
        return cells;
    }

    getBlock(selectedCell) {
        return parseCellKey(selectedCell);
    }

    getCellsInfo(selectedCells) {
        const cellsInfo = [];
        const colsInfo = {};
        for (const selectedCell of selectedCells) {
            const { startRow, startCol } = this.getBlock(selectedCell);
            const rowId = this.rowIdsByFirstRow[startRow];
            if (!rowId) {
                continue;
            }
            if (!colsInfo[startCol]) {
                let { start, stop } = this.getSubColumnFromColNumber(startCol);
                ({ start, stop } = this.normalizeTimeRange(start, stop));
                colsInfo[startCol] = { start, stop };
            }
            const { start, stop } = colsInfo[startCol];
            cellsInfo.push({ rowId, start, stop });
        }
        return cellsInfo;
    }

    onMultiCreate(multiCreateData, selectedCells) {
        const cellsInfo = this.getCellsInfo(selectedCells);
        return this.model.multiCreateRecords(multiCreateData, cellsInfo);
    }
}
