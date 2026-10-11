/** @odoo-module native */
import { markup, observe, proxy, useListener } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { compareDates, toDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { throttleForAnimation } from "@web/core/utils/timing";
import { usePopover } from "@web/ui/popover";

import {
    dateAddFixedOffset,
    getCellsOnRow,
    getHoveredCellPart,
    useGanttDraggable,
    useGanttResizable,
    useGanttUndraggable,
    useMultiHover,
} from "./gantt_helpers.js";
import { GanttRendererConnectors } from "./gantt_renderer_connectors.js";
import { rtl } from "./gantt_renderer_core.js";

const INTERACTION_CLASSNAMES = [
    ["connect", "o_connect"],
    ["copy", "o_copying"],
    ["locked", "o_grabbing_locked"],
    ["reschedule", "o_grabbing"],
    ["resize", "o_resizing"],
];
const clearObject = (obj) => {
    for (const key in obj) {
        delete obj[key];
    }
};

const log = makeLogger("gantt.interaction");

export class GanttRendererInteractions extends GanttRendererConnectors {
    setup() {
        super.setup();

        /** @type {HoveredInfo} */
        this.hovered = {
            connector: null,
            hoverable: null,
            pill: null,
            collapsableColumnHeader: null,
        };

        /** @type {Interaction} */
        this.interaction = observe(
            {
                mode: null,
                dragAction: "reschedule",
            },
            () => this.onInteractionChange(),
        );
        this.onInteractionChange();
        /** @type {ResizeBadge} */
        this.timeDisplayBadgeReactiveStart = proxy({});
        this.timeDisplayBadgeReactiveStop = proxy({});
        this.cursorPosition = {
            x: 0,
            y: 0,
        };
        this.popover = usePopover(this.constructor.components.Popover, {
            onClose: () => {
                if (!this.preventClick) {
                    this.preventClick = true;
                    setTimeout(() => (this.preventClick = false), 250);
                }
                this.onCloseCurrentPopover?.();
            },
        });

        this.throttledComputeHoverParams = throttleForAnimation((ev) =>
            this.computeHoverParams(ev),
        );
        useListener(window, "keydown", (ev) => this.onWindowKeyDown(ev));
        useListener(window, "keyup", (ev) => this.onWindowKeyUp(ev));
        useListener(window, "blur", () => this.releaseCopyModifier());
        useMultiHover({
            ref: this.gridRef,
            selector: ".o_gantt_group",
            exception: "o_gantt_cell_folded",
            related: ["data-row-id"],
            className: "o_gantt_group_hovered",
        });
        this.cellForDrag = { el: null, part: 0 };
        const dragState = useGanttDraggable(this.pillDragOptions());
        const resizeState = useGanttResizable(this.pillResizeOptions());
        this.dragStates = [dragState, resizeState];

        if (!this.model.hasMultiCreate) {
            const unDragState = useGanttUndraggable({
                ref: this.gridRef,
                elements: ".o_undraggable",
                ignore: ".o_resize_handle,.o_connector_creator_bullet",
                edgeScrolling: { enabled: false },
                onWillStartDrag: this.cleanMultiSelection.bind(this),
                onDragStart: () => {
                    this.interaction.mode = "locked";
                },
                onDragEnd: () => {
                    this.interaction.mode = null;
                },
            });
            this.dragStates.push(unDragState);
        }
        useLayoutEffect(
            (content) => {
                content.addEventListener("scroll", this.throttledComputeHoverParams);
                return () => {
                    content.removeEventListener(
                        "scroll",
                        this.throttledComputeHoverParams,
                    );
                };
            },
            () => [this.gridRef.el?.parentElement],
        );
    }

    pillDragOptions() {
        const scale = () => this.model.metaData.scale;
        return {
            enable: () => Boolean(this.cellForDrag.el),
            ref: this.gridRef,
            hoveredCell: this.cellForDrag,
            elements: ".o_draggable",
            ignore: ".o_resize_handle,.o_connector_creator_bullet",
            cells: ".o_gantt_cell:not(.o_gantt_readonly)",
            cellDragClassName: "o_gantt_cell o_drag_hover",
            ghostClassName: "o_dragged_pill_ghost",
            rtl,
            scale,
            getBadgesInitialDates: () => ({
                start: this.badgeInitialStartDate,
                stop: this.badgeInitialStopDate,
            }),
            addStickyCoordinates: this.addStickyCoordinates.bind(this),
            onWillStartDrag: this.cleanMultiSelection.bind(this),
            onDragStart: ({ pill }) => {
                this.initBadges(pill);
                this.popover.close();
                this.setStickyPill(pill);
                this.toggleRowsReadonly(false);
                this.interaction.mode = "drag";
            },
            onDrag: this.updateBadges.bind(this),
            onDragEnd: () => {
                this.clearBadges();
                this.toggleRowsReadonly(true);
                this.setStickyPill();
                this.removeStickyCoordinates();
                this.interaction.mode = null;
            },
            onDrop: (params) => this.dragPillDrop(params),
        };
    }

    pillResizeOptions() {
        const scale = () => this.model.metaData.scale;
        return {
            ref: this.gridRef,
            hoveredCell: this.cellForDrag,
            elements: ".o_resizable",
            innerPills: ".o_gantt_pill",
            handles: "o_resize_handle",
            edgeScrolling: { speed: 40, threshold: 150, direction: "horizontal" },
            scale,
            getBadgesInitialDates: () => ({
                start: this.badgeInitialStartDate,
                stop: this.badgeInitialStopDate,
            }),
            showHandles: (pillEl) => {
                const pill = this.pills[pillEl.dataset.pillId];
                const hideHandles = this.connectorDragState.dragging;
                return {
                    start: !pill.disableStartResize && !hideHandles,
                    end: !pill.disableStopResize && !hideHandles,
                };
            },
            rtl,
            onWillStartDrag: this.cleanMultiSelection.bind(this),
            onDragStart: ({ pill, addClass }) => {
                this.initBadges(pill);
                this.popover.close();
                this.setStickyPill(pill);
                addClass(pill, "o_resized");
                this.interaction.mode = "resize";
            },
            onDrag: this.updateBadges.bind(this),
            onDragEnd: ({ pill, removeClass }) => {
                this.clearBadges();
                this.setStickyPill();
                removeClass(pill, "o_resized");
                this.interaction.mode = null;
            },
            onDrop: (params) => this.resizePillDrop(params),
        };
    }

    get isDragging() {
        return this.dragStates.some((s) => s.dragging);
    }

    computeDerivedParamsFromHover() {
        const { scale } = this.model.metaData;

        const { connector, collapsableColumnHeader, hoverable } = this.hovered;

        const isCellHovered = hoverable?.matches(".o_gantt_cell");
        this.cellForDrag.el = isCellHovered ? hoverable : null;
        this.cellForDrag.part = 0;
        if (isCellHovered && scale.cellPart > 1) {
            this.cellForDrag.part = getHoveredCellPart(
                hoverable,
                this.cursorPosition.x,
                scale.cellPart,
                rtl(),
            );
        }

        if (this.isDragging) {
            this.progressBarsReactive.hoveredRowId = null;
            return;
        }

        if (!this.connectorDragState.dragging) {
            const hoveredConnectorId = connector?.dataset.connectorId || null;
            if (
                this.highlightedConnectorId &&
                this.highlightedConnectorId !== hoveredConnectorId
            ) {
                this.toggleConnectorHighlighting(this.highlightedConnectorId, false);
            }
            if (hoveredConnectorId) {
                this.progressBarsReactive.hoveredRowId = null;
                return this.toggleConnectorHighlighting(hoveredConnectorId, true);
            }
        }

        this.toggleCollapsableColumnHeaderHighlighting(collapsableColumnHeader);
        this.progressBarsReactive.hoveredRowId =
            hoverable && !hoverable.classList.contains("o_gantt_cell_folded")
                ? hoverable.dataset.rowId
                : null;
    }

    get isAutoPlan() {
        return ["consumeBuffer", "maintainBuffer"].includes(
            this.model.metaData.rescheduleMethod,
        );
    }

    /**
     * @param {Object} params
     * @param {Element} params.pill
     * @param {Element} params.cellSrc
     * @param {Element} params.cellDst
     * @param {number} params.diff
     */
    async dragPillDrop({ pill, cellSrc, cellDst, diff }) {
        const { rowId } = cellDst.dataset;
        log.logic("dragPillDrop", () => ({
            pill: pill.dataset.pillId,
            from: cellSrc.dataset.rowId,
            to: rowId,
            diff,
            action: this.interaction.dragAction,
        }));
        const { dateStartField, dateStopField, scale } = this.model.metaData;
        const { cellTime, time } = scale;
        const { record } = this.pills[pill.dataset.pillId];
        const params = this.getScheduleParams(pill);
        const isCopyMode = this.interaction.dragAction === "copy";
        if (!isCopyMode && !diff && cellSrc.dataset.rowId === rowId) {
            return;
        }

        params.start =
            (diff || isCopyMode) &&
            dateAddFixedOffset(toDateTime(record[dateStartField]), {
                [time]: cellTime * diff,
            });
        params.stop =
            (diff || isCopyMode) &&
            dateAddFixedOffset(toDateTime(record[dateStopField]), {
                [time]: cellTime * diff,
            });
        params.rowId = rowId;

        const schedule = this.model.getSchedule(params);

        let copyResId;
        let fallbackSchedule;
        if (isCopyMode) {
            copyResId = await this.model.copy(
                record.id,
                schedule,
                this.openPlanDialogCallback.bind(this),
            );
        } else {
            const fallbackParams = {
                ...this.getUndoAfterDragRecordData(record),
                rowId: cellSrc.dataset.rowId,
            };
            fallbackSchedule = this.model.getSchedule(fallbackParams);
            if (this.isAutoPlan) {
                await this.model.rescheduleAccordingToDependency(
                    record.id,
                    schedule,
                    this.rescheduleAccordingToDependencyCallback.bind(this),
                );
            } else {
                await this.model.reschedule(
                    record.id,
                    schedule,
                    this.openPlanDialogCallback.bind(this),
                );
            }
        }

        if (cellDst.classList.contains("o_gantt_group") && this.model.isClosed(rowId)) {
            this.model.toggleRow(rowId);
        }

        this.displayUndoNotificationAfterDrag(
            copyResId || record.id,
            this.interaction.dragAction,
            fallbackSchedule,
        );
    }

    /**
     * @param {number} resId
     * @param {string} dragAction
     * @param {Object} [fallbackData]
     */
    displayUndoNotificationAfterDrag(resId, dragAction, fallbackData = {}) {
        if (!(dragAction === "copy" || dragAction === "reschedule")) {
            return;
        }
        if (dragAction === "reschedule" && this.isAutoPlan) {
            return;
        }
        const messages = this.getUndoAfterDragMessages(dragAction);
        this.closeNotificationFn?.();
        this.closeNotificationFn = this.notificationService.add(
            markup`<i class="fa-solid fa-check"></i><span class="ms-1">${messages.success}</span>`,
            {
                type: "success",
                buttons: [
                    {
                        name: _t("Undo"),
                        icon: "fa-undo",
                        onClick: async () => {
                            const result = await this.orm.call(
                                this.model.metaData.resModel,
                                "gantt_undo_drag_drop",
                                [resId, dragAction, fallbackData],
                            );
                            this.closeNotificationFn?.();
                            if (result) {
                                this.closeNotificationFn = this.notificationService.add(
                                    markup`<i class="fa-solid fa-check"></i><span class="ms-1">${messages.undo}</span>`,
                                    { type: "success" },
                                );
                            } else {
                                this.closeNotificationFn = this.notificationService.add(
                                    markup`<i class="fa-solid fa-xmark"></i><span class="ms-1">${messages.failure}</span>`,
                                    { type: "danger" },
                                );
                            }
                            this.model.fetchData();
                        },
                    },
                ],
            },
        );
    }

    /**
     * @param {string} dragAction
     * @returns {Object}
     */
    getUndoAfterDragMessages(dragAction) {
        if (dragAction === "copy") {
            return {
                success: _t("Record duplicated"),
                undo: _t("Record removed"),
                failure: _t("Record could not be removed"),
            };
        }
        return {
            success: _t("Record rescheduled"),
            undo: _t("Record reschedule undone"),
            failure: _t("Failed to undo reschedule"),
        };
    }

    /**
     * @param {Object} record
     * @returns {Object}
     */
    getUndoAfterDragRecordData(record) {
        const { dateStartField, dateStopField } = this.model.metaData;
        return {
            start: record[dateStartField],
            stop: record[dateStopField],
        };
    }

    /**
     * Get schedule parameters
     *
     * @param {Element} pill
     * @returns {Object} - An object containing parameters needed for scheduling the pill.
     */
    getScheduleParams(pill) {
        return {};
    }

    /**
     * @param {Object} params
     * @param {Element} params.pill
     * @param {number} params.diff
     * @param {"start" | "end"} params.direction
     */
    async resizePillDrop({ pill, diff, direction }) {
        log.logic("resizePillDrop", () => ({
            pill: pill.dataset.pillId,
            diff,
            direction,
        }));
        const { dateStartField, dateStopField, scale } = this.model.metaData;
        const { cellTime, time } = scale;
        const { record } = this.pills[pill.dataset.pillId];
        const params = this.getScheduleParams(pill);

        const recordStart = toDateTime(record[dateStartField]);
        const recordStop = toDateTime(record[dateStopField]);
        if (direction === "start") {
            params.start = dateAddFixedOffset(recordStart, {
                [time]: cellTime * diff,
            });
            if (compareDates(params.start, recordStop) > 0) {
                return this.notificationService.add(
                    _t("Starting date cannot be after the ending date"),
                    {
                        type: "warning",
                    },
                );
            }
        } else {
            params.stop = dateAddFixedOffset(recordStop, {
                [time]: cellTime * diff,
            });
            if (compareDates(params.stop, recordStart) < 0) {
                return this.notificationService.add(
                    _t("Ending date cannot be before the starting date"),
                    {
                        type: "warning",
                    },
                );
            }
        }
        const schedule = this.model.getSchedule(params);
        const fallbackParams = this.getUndoAfterDragRecordData(record);
        const fallbackSchedule = this.model.getSchedule(fallbackParams);

        await this.model.reschedule(
            record.id,
            schedule,
            this.openPlanDialogCallback.bind(this),
        );
        this.displayUndoNotificationAfterDrag(
            record.id,
            this.interaction.dragAction,
            fallbackSchedule,
        );
    }

    /**
     * @param {HTMLElement} [pillEl]
     */
    setStickyPill(pillEl) {
        this.stickyPillId = pillEl ? pillEl.dataset.pillId : null;
    }

    /**
     * @param {boolean} addReadonly: whether to add or remove the readonly class
     */
    toggleRowsReadonly(addReadonly) {
        if (!this.stickyPillId || !this.containsReadonlyGroup()) {
            return;
        }
        const startingRowId = this.pills[this.stickyPillId].rowId;
        const rowIdx = this.rows.findIndex((r) => r.id === startingRowId);
        this.toggleReadonly(this.rows[rowIdx], addReadonly);
        if (this.rows[rowIdx].readonlyChild) {
            for (const row of this.rows.slice(0, rowIdx).reverse()) {
                if (!row.readonlyChild) {
                    break;
                }
                this.toggleReadonly(row, addReadonly);
            }
            for (const row of this.rows.slice(rowIdx + 1, this.rows.length)) {
                if (!row.readonlyChild) {
                    break;
                }
                this.toggleReadonly(row, addReadonly);
            }
        }
    }

    toggleReadonly(row, addReadonly) {
        for (const cell of getCellsOnRow(this.gridRef.el, row.id)) {
            if (addReadonly) {
                cell.classList.add("o_gantt_readonly");
            } else {
                cell.classList.remove("o_gantt_readonly");
            }
        }
    }

    initBadges(pill) {
        const { dateStartField, dateStopField } = this.model.metaData;
        const { record } = this.pills[pill.dataset.pillId];
        this.badgeInitialStartDate = toDateTime(record[dateStartField]);
        this.badgeInitialStopDate = toDateTime(record[dateStopField]);
    }

    updateBadges({ startBadge, stopBadge }) {
        Object.assign(this.timeDisplayBadgeReactiveStart, startBadge);
        Object.assign(this.timeDisplayBadgeReactiveStop, stopBadge);
    }

    clearBadges() {
        clearObject(this.timeDisplayBadgeReactiveStart);
        clearObject(this.timeDisplayBadgeReactiveStop);
        delete this.badgeInitialStartDate;
        delete this.badgeInitialStopDate;
    }

    onInteractionChange() {
        let { dragAction, mode } = this.interaction;
        if (mode === "drag") {
            mode = dragAction;
        }
        if (this.gridRef.el) {
            for (const [action, className] of INTERACTION_CLASSNAMES) {
                this.gridRef.el.classList.toggle(className, mode === action);
            }
        }
    }

    onPointerLeave() {
        this.throttledComputeHoverParams.cancel();

        if (!this.isDragging) {
            const hoveredConnectorId = this.hovered.connector?.dataset.connectorId;
            this.toggleConnectorHighlighting(hoveredConnectorId, false);

            this.toggleCollapsableColumnHeaderHighlighting(null);
        }

        this.hovered.connector = null;
        this.hovered.pill = null;
        this.hovered.hoverable = null;
        this.hovered.collapsableColumnHeader = null;

        this.computeDerivedParamsFromHover();
    }

    /**
     * Updates all hovered elements, then calls "computeDerivedParamsFromHover".
     *
     * @see computeDerivedParamsFromHover
     * @param {Event} ev
     */
    computeHoverParams(ev) {
        let els = null;
        let position = {};
        if (ev.type === "scroll") {
            position = this.cursorPosition;
        } else {
            position.x = ev.clientX;
            position.y = ev.clientY;
            this.cursorPosition = position;
        }
        const pointedEls = () =>
            els || (els = document.elementsFromPoint(position.x, position.y));

        const find = (selector) =>
            ev.target.closest?.(selector) ||
            pointedEls().find((el) => el.matches(selector)) ||
            null;

        this.hovered.connector = find(".o_gantt_connector");
        this.hovered.hoverable = find(".o_gantt_hoverable");
        this.hovered.pill = find(".o_gantt_pill_wrapper");
        this.hovered.collapsableColumnHeader = find(".o_gantt_foldable");

        this.computeDerivedParamsFromHover();
    }

    /**
     * @param {KeyboardEvent} ev
     * @param {Pill} pill
     */
    onPillKeydown(ev, pill) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.onPillClicked(ev, pill);
        }
    }

    rescheduleAccordingToDependencyCallback(result) {
        const isWarning = result.type === "warning";
        this.closeNotificationFn?.();
        const icon = isWarning ? "fa-warning" : "fa-check";
        this.closeNotificationFn = this.notificationService.add(
            markup`<i class="fa ${icon}"></i><span class="ms-1">${result["message"]}</span>`,
            {
                type: result["type"],
                sticky: true,
                buttons:
                    isWarning || !result.old_vals_per_pill_id
                        ? []
                        : [
                              {
                                  name: _t("Undo"),
                                  icon: "fa-undo",
                                  onClick: async () => {
                                      const ids = Object.keys(
                                          result["old_vals_per_pill_id"],
                                      ).map(Number);
                                      await this.orm.call(
                                          this.model.metaData.resModel,
                                          "action_rollback_scheduling",
                                          [ids, result["old_vals_per_pill_id"]],
                                      );
                                      this.closeNotificationFn();
                                      await this.model.fetchData();
                                  },
                              },
                          ],
            },
        );
    }

    /**
     * @param {KeyboardEvent} ev
     */
    onWindowKeyDown(ev) {
        if (ev.key === "Control") {
            this.prevDragAction =
                this.interaction.dragAction === "copy"
                    ? "reschedule"
                    : this.interaction.dragAction;
            this.interaction.dragAction = "copy";
            this.ctrlPressed = true;
        }
    }

    /**
     * @param {KeyboardEvent} ev
     */
    onWindowKeyUp(ev) {
        if (ev.key === "Control") {
            this.releaseCopyModifier();
        }
    }

    releaseCopyModifier() {
        if (!this.ctrlPressed) {
            return;
        }
        this.interaction.dragAction = this.prevDragAction || "reschedule";
        this.ctrlPressed = false;
    }

    onWillUnmount() {
        this.throttledComputeHoverParams.cancel();
        this.closeNotificationFn?.();
    }
}
