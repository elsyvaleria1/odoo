/** @odoo-module native */
import { markup, onWillStart, proxy } from "@odoo/owl";
import { AddressRecurrencyConfirmationDialog } from "@planning/components/address_recurrency_confirmation_dialog/address_recurrency_confirmation_dialog";
import { RESOURCE_TYPE_ICONS } from "@web/components/resource_avatar/resource_type_icons";
import { formatFloatTime } from "@web/core/formatters";
import {
    compareDates,
    fromEpochMilliseconds,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { ConfirmationDialog } from "@web/ui/dialog";
import { getColumnStart, getUnionOfIntersections } from "@web_gantt/gantt_helpers";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

import { planningAskRecurrenceUpdate } from "../planning_calendar/planning_ask_recurrence_update/planning_ask_recurrence_update_hook.js";
import { usePlanningRecurringDeleteAction } from "../planning_hooks.js";
import { PlanningEmployeeAvatar } from "./planning_employee_avatar.js";
import { PlanningGanttRendererControls } from "./planning_gantt_renderer_controls.js";
import { PlanningGanttRowProgressBar } from "./planning_gantt_row_progress_bar.js";
import { PlanningResourceName } from "./planning_resource_name.js";
import { PlanningSplitTool } from "./planning_split_tool.js";

/** Hours from milliseconds, rounded to five minutes. */
function roundedHours(millis) {
    const minutes = Math.round(millis / 60_000 / 5) * 5;
    return minutes / 60;
}

/** @param {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} interval */
function intervalMilliseconds([start, stop]) {
    return stop.epochMilliseconds - start.epochMilliseconds;
}

export class PlanningGanttRenderer extends GanttRenderer {
    static template = "planning.PlanningGanttRenderer";
    static rowHeaderTemplate = "planning.PlanningGanttRenderer.RowHeader";
    static pillTemplate = "planning.PlanningGanttRenderer.Pill";
    static groupPillTemplate = "planning.PlanningGanttRenderer.GroupPill";
    static components = {
        ...GanttRenderer.components,
        Avatar: PlanningEmployeeAvatar,
        GanttRendererControls: PlanningGanttRendererControls,
        GanttRowProgressBar: PlanningGanttRowProgressBar,
        ResourceName: PlanningResourceName,
        PlanningSplitTool,
    };
    setup() {
        this.duplicateToolHelperReactive = proxy({ shouldDisplay: false });
        this.splitToolHelperReactive = proxy({});
        super.setup();
        this.ui = useService("ui");
        useLayoutEffect(() => {
            this.gridRef.el.classList.add("o_planning_gantt");
        });

        this.state = proxy({
            recurrenceUpdate: "this",
        });
        this.planningRecurrenceDeletion = usePlanningRecurringDeleteAction();
        this.isPlanningManager = false;
        this.notificationService = useService("notification");
        onWillStart(this.onWillStart);
    }

    async onWillStart() {
        this.isPlanningManager = await user.hasGroup("planning.group_planning_manager");
    }

    /**
     * @override
     */
    addTo(pill, group) {
        if (!pill.allocatedHours[group.col]) {
            return false;
        }
        group.pills.push(pill);
        group.aggregateValue += pill.allocatedHours[group.col];
        return true;
    }

    computeDerivedParams() {
        this.rowsWithResourceName = {};
        super.computeDerivedParams();
    }

    onPillClicked(ev, pill) {
        if (this.ui.isTouch || !this.isPlanningManager || this.model.useSampleModel) {
            super.onPillClicked(...arguments);
            return;
        }
        // Decided from the click's own position, not from the rendered split
        // tool: the tool is painted a frame after the pointer reaches the
        // border, so a click in between would open the popover instead.
        const cellEl =
            ev.clientX === undefined
                ? null
                : document
                      .elementsFromPoint(ev.clientX, ev.clientY)
                      .find((el) => el.matches(".o_gantt_cell"));
        const splitCol = cellEl && this.getSplitColumn(pill, cellEl, ev.clientX);
        if (splitCol) {
            this.onPillSplitToolClicked(pill, splitCol);
            delete this.splitToolHelperReactive.position;
            this.popover.close();
            return;
        }
        super.onPillClicked(...arguments);
    }

    computeDerivedParamsFromHover() {
        super.computeDerivedParamsFromHover(...arguments);
        delete this.splitToolHelperReactive.position;
        if (this.ui.isTouch || !this.isPlanningManager || this.model.useSampleModel) {
            return;
        }
        if (this.isDragging || this.connectorDragState.dragging) {
            return;
        }
        const { pill: pillEl } = this.hovered;
        const { el: cellEl } = this.cellForDrag;
        if (pillEl && cellEl) {
            const pill = this.pills[pillEl.dataset.pillId];
            const col = this.getSplitColumn(pill, cellEl, this.cursorPosition.x);
            if (col) {
                this.splitToolHelperReactive.position = this.getGridPosition({
                    row: pill.grid.row,
                    column: [col, col + 1],
                });
            }
        }
    }

    /** The column a pointer at `x` over `cellEl` splits `pill` at: a border of the cell inside the pill, or none. */
    getSplitColumn(pill, cellEl, x) {
        const rtl = localization.direction === "rtl";
        const { x: cellX, width } = cellEl.getBoundingClientRect();
        const startBorder = rtl ? cellX + width : cellX;
        const endBorder = startBorder + (rtl ? -1 : 1) * width;
        let col = getColumnStart(getComputedStyle(cellEl));
        if (Math.abs(endBorder - x) <= 8) {
            col += 1;
        } else if (Math.abs(startBorder - x) > 8) {
            return null;
        }
        return pill.grid.column.includes(col) ? null : col;
    }

    /**
     * A planning slot's duration is its allocated hours. This is a fact about
     * the model, not a per-view choice, so it holds whether or not a given arch
     * names a `duration_field` -- the arch attribute stays available to any
     * gantt that wants to override it.
     *
     * @override
     */
    getPillDuration(record) {
        return super.getPillDuration(record) || record.allocated_hours || 0;
    }

    /**
     * @override
     */
    getDurationStr(record) {
        const { allocated_hours, allocated_percentage } = record;
        return allocated_percentage !== 100 && allocated_hours
            ? super.getDurationStr(...arguments)
            : "";
    }

    getSpan({ grid }) {
        const { column } = grid;
        return column[1] - column[0];
    }

    /**
     * @override
     */
    enrichPill() {
        const pill = super.enrichPill(...arguments);
        const { record } = pill;
        const avatar = this.pillAvatar(record);
        pill.hasAvatar = Boolean(avatar);
        pill.avatarProps = avatar || {};

        const model = this.props.model;
        if (model.highlightIds && !model.highlightIds.includes(record.id)) {
            pill.className += " opacity-25";
        }
        pill.allocatedHours = {};
        const percentage = record.allocated_percentage
            ? record.allocated_percentage / 100
            : 0;
        if (percentage === 0) {
            return pill;
        }
        const resourceId = record.resource_id && record.resource_id.id;
        if (this.isOpenShift(record) || this.isFlexibleHours(resourceId)) {
            this.spreadAllocatedHours(pill);
        } else {
            this.intersectAllocatedHours(pill, percentage);
        }
        return pill;
    }

    pillAvatar(record) {
        if (
            !record.employee_id ||
            this.model.metaData.groupedBy.includes("resource_id")
        ) {
            return null;
        }
        const { id: resId, display_name: displayName } = record.employee_id;
        return { resModel: "hr.employee", resId, displayName };
    }

    /** The allocated hours of a shift with no work intervals, spread evenly over its columns. */
    spreadAllocatedHours(pill) {
        const { record } = pill;
        for (
            let col = this.getFirstGridCol(pill);
            col < this.getLastGridCol(pill);
            col++
        ) {
            const subColumn = this.getSubColumnFromColNumber(col);
            if (!subColumn) {
                continue;
            }
            const { start, stop } = subColumn;
            const maxDuration = intervalMilliseconds([start, stop]);
            const toMillisRatio = 60 * 60 * 1000;
            const dailyAllocHours = Math.min(
                (record.allocated_hours * toMillisRatio) / this.getSpan(pill),
                maxDuration,
            );
            if (dailyAllocHours) {
                pill.allocatedHours[col] = roundedHours(dailyAllocHours);
            }
        }
    }

    /** The allocated hours of a shift per column, from its work intervals. */
    intersectAllocatedHours(pill, percentage) {
        const { record } = pill;
        // An employee working outside their work intervals (no work hours) has
        // none to intersect: the shift itself is the interval, at the ratio of
        // its allocated hours to its length.
        let recordIntervals = this.getRecordIntervals(record);
        if (!recordIntervals.length) {
            recordIntervals = [[record.start_datetime, record.end_datetime]];
            percentage =
                (record.allocated_hours * 3.6e6) /
                intervalMilliseconds([record.start_datetime, record.end_datetime]);
        }
        for (
            let col = this.getFirstGridCol(pill) - 1;
            col <= this.getLastGridCol(pill);
            col++
        ) {
            const subColumn = this.getSubColumnFromColNumber(col);
            if (!subColumn) {
                continue;
            }
            const { start, stop } = subColumn;
            const interval = [start, stop.add({ seconds: 1 })];
            const union = getUnionOfIntersections(interval, recordIntervals);
            let duration = 0;
            for (const otherInterval of union) {
                duration += intervalMilliseconds(otherInterval);
            }
            if (duration) {
                pill.allocatedHours[col] = roundedHours(duration * percentage);
            }
        }
    }

    getResourceNameProps(row) {
        return this.rowsWithResourceName[row.id];
    }

    /**
     * @override
     */
    getAggregateValue(group, previousGroup) {
        return group.aggregateValue + previousGroup.aggregateValue;
    }

    /**
     * @override
     */
    getScheduleParams(pill) {
        const { record } = this.pills[pill.dataset.pillId];
        return { recurrence_update: record.recurrence_update };
    }

    /**
     * @override
     */
    getGroupPillDisplayName(pill) {
        return formatFloatTime(pill.aggregateValue);
    }

    /**
     * @override
     */
    async getPopoverProps(pill) {
        const popoverProps = await super.getPopoverProps(...arguments);
        const { record } = pill;
        if (this.isPlanningManager) {
            const recurrenceProps = {
                resId: record.id,
                resModel: this.model.metaData.resModel,
            };
            popoverProps.buttons.push({
                text: _t("Delete"),
                class: "btn btn-sm btn-secondary btn-delete",
                onClick: async () => {
                    const canProceed = await new Promise((resolve) => {
                        if (record.repeat) {
                            this.dialogService.add(
                                AddressRecurrencyConfirmationDialog,
                                {
                                    cancel: () => resolve(false),
                                    close: () => resolve(false),
                                    confirm: async () => {
                                        await this.planningRecurrenceDeletion._actionAddressRecurrency(
                                            recurrenceProps,
                                            this.state.recurrenceUpdate,
                                        );
                                        return resolve(true);
                                    },
                                    onChangeRecurrenceUpdate:
                                        this.planningRecurrenceDeletion._setRecurrenceUpdate.bind(
                                            this,
                                        ),
                                    selected: this.state.recurrenceUpdate,
                                },
                            );
                        } else {
                            this.dialogService.add(ConfirmationDialog, {
                                body: _t("Are you sure you want to delete this shift?"),
                                confirmLabel: _t("Delete"),
                                cancel: () => resolve(false),
                                close: () => resolve(false),
                                confirm: () => resolve(true),
                            });
                        }
                    });
                    if (canProceed) {
                        await this.model.orm.unlink(recurrenceProps.resModel, [
                            recurrenceProps.resId,
                        ]);
                        await this.model.fetchData();
                    }
                },
            });
        }
        return popoverProps;
    }

    /**
     * @param {RelationalRecord} record
     * @returns {any[]}
     */
    getRecordIntervals(record) {
        const resourceId = record.resource_id && record.resource_id.id;
        const startTime = record.start_datetime;
        const endTime = record.end_datetime;
        if (!Object.keys(this.model.data.progressBars.resource_id || {}).length) {
            return [];
        }
        const resourceIntervals =
            this.model.data.progressBars?.resource_id?.[resourceId]?.work_intervals;
        if (!resourceIntervals) {
            return [];
        }
        const recordIntervals = getUnionOfIntersections(
            [startTime, endTime],
            resourceIntervals,
        );
        return recordIntervals;
    }

    /**
     * @param {number} resource_id
     * @returns {boolean}
     */
    isFlexibleHours(resource_id) {
        return !!this.model.data.progressBars?.resource_id?.[resource_id]
            ?.is_flexible_hours;
    }

    /**
     * @param {RelationalRecord} record
     * @returns {boolean}
     */
    isOpenShift(record) {
        return !record.resource_id;
    }

    /**
     * By default in the gantt view we show aggregation info in the columns that have pills inside.
     * In the planning gantt view we colour the group rows based on whether the resource is under/over planned for a day.
     * This requires the aggregation info to remain visible even in the absence of pills.
     *
     * The checks below are done in this order because of their priority importance:
     * (no working intervals > flex-hours / pill present > non-working days > time-off)
     * @override
     */
    shouldAggregate(row, g) {
        const wouldAggregate = super.shouldAggregate(...arguments);
        if (!wouldAggregate) {
            return false;
        }

        // These checks only make sense if the gantt view is grouped by the resource
        if (row.groupedBy && row.groupedBy[0] !== "resource_id") {
            return wouldAggregate;
        }

        // A row not having work intervals could mean that a resource doesn't have a contract or the row is the "Total" row
        const workIntervals =
            this.model.data.progressBars?.resource_id?.[row.resId]?.work_intervals;
        if (!workIntervals) {
            if (row.groupedByField === "resource_id") {
                // If there is no contract, don't show aggregate info
                return false;
            } else if (!row.groupedByField) {
                // If it's not grouped by anything, its the total row, follow default behaviour
                return wouldAggregate;
            }
        }

        // We show aggregation info in all columns for flexible-hour employees and when there are pills in that day
        if ((row.resId && !row.unavailabilities) || wouldAggregate) {
            return true;
        }

        // We do not show aggregate info on non-working days
        const group = this.getSubColumnFromColNumber(g.grid.column[0]);
        const groupWorkOverlap = getUnionOfIntersections(
            [group.start, group.stop],
            workIntervals,
        );
        if (!groupWorkOverlap.length) {
            return false;
        }

        // We do not show aggregate info on days with time-off
        const unavailabilities = Object.entries(row.unavailabilities).map(
            ([key, { start, stop }]) => [start, stop],
        );
        const dayOff = [];
        for (const interval of groupWorkOverlap) {
            const dayOffInterval = getUnionOfIntersections(interval, unavailabilities);
            if (dayOffInterval.length) {
                dayOff.push(dayOffInterval);
            }
        }
        if (dayOff.length === groupWorkOverlap.length) {
            for (const [i, interval] of dayOff.entries()) {
                if (
                    compareDates(interval[0], groupWorkOverlap[i][0]) <= 0 &&
                    compareDates(interval[1], groupWorkOverlap[i][1]) >= 0
                ) {
                    return false;
                }
            }
        }
        return true;
    }

    /**
     * @override
     */
    getPillFromGroup(group, consolidate) {
        const newPill = super.getPillFromGroup(...arguments);
        if (group.pills.length) {
            newPill.resourceId = group.pills[0].record.resource_id;
        }
        const { start, stop } = this.getColumnFromColNumber(newPill.grid.column[0]);
        newPill.date_start = start;
        newPill.date_end = stop;
        return newPill;
    }

    _computeWorkHours(pill, row) {
        let workHours = 0;
        if (
            !row.progressBar?.employee_id ||
            ["day", "year"].includes(this.model.metaData.scale.id)
        ) {
            return workHours;
        }
        const resource_id = row.resId;
        // If flexible hour contract, colour the gantt view group based on whether the aggregate value > the "average work hours" per day.
        if (this.isFlexibleHours(resource_id)) {
            workHours =
                this.model.data.progressBars.resource_id[resource_id]?.avg_hours;
        } else {
            workHours = this.model.data.progressBars.resource_id[
                resource_id
            ]?.work_intervals.reduce((sum, [intervalStart, intervalEnd]) => {
                // Check whether the work interval is of the same date as the grouping pill
                if (
                    compareDates(intervalStart, pill.date_start) >= 0 &&
                    compareDates(intervalEnd, pill.date_end) <= 0
                ) {
                    sum += intervalMilliseconds([intervalStart, intervalEnd]) / 3.6e6;
                }
                return sum;
            }, 0);
        }
        return workHours;
    }

    _computeDisplayName(pill, workHours, row) {
        const progressBar = row.progressBar;
        if (
            !progressBar?.employee_id ||
            ["day", "month", "year"].includes(this.model.metaData.scale.id) ||
            workHours === 0
        ) {
            return pill.displayName;
        }
        return `${pill.displayName} (${Math.round((pill.aggregateValue / workHours) * 100)}%)`;
    }

    _computeResourceOvertimeColors(pill, workHours, row) {
        const progressBar = row.progressBar;
        const isFullyFlexibleHours =
            this.isFlexibleHours(row.resId) && workHours === 24;
        if (
            !progressBar?.employee_id ||
            ["day", "year"].includes(this.model.metaData.scale.id) ||
            isFullyFlexibleHours
        ) {
            return "bg-primary border-primary";
        }
        return workHours === pill.aggregateValue
            ? "bg-success border-success"
            : workHours > pill.aggregateValue
              ? "bg-warning border-warning"
              : "bg-danger border-danger";
    }

    hasResourceName(row) {
        return row.id in this.rowsWithResourceName;
    }

    /**
     * @override
     */
    isDisabled(row = null) {
        if (row && !row.fromServer && row.groupLevel === 0) {
            return false;
        }
        return super.isDisabled(...arguments);
    }

    /**
     * @override
     */
    isHoverable(row) {
        if (!row.fromServer) {
            return !row.isGroup;
        }
        return super.isHoverable(...arguments);
    }

    getRowAvatar(row) {
        const { fromServer, groupedByField, id, name, progressBar, resId } = row;
        const isGroupedByResource = groupedByField === "resource_id";
        const employeeId = progressBar && progressBar.employee_id;
        const resourceIcon = RESOURCE_TYPE_ICONS[progressBar?.resource_type];
        const showEmployeeAvatar =
            (isGroupedByResource && fromServer && Boolean(employeeId)) ||
            Boolean(resId && resourceIcon);
        if (showEmployeeAvatar) {
            const { fields } = this.model.metaData;
            return {
                resModel: fields.resource_id.relation,
                resId,
                displayName: name,
                resourceIcon,
                showPopover: !resourceIcon || progressBar.has_several_roles,
                resourceColor: (progressBar && progressBar.resource_color) || 0,
            };
        }
        if (resourceIcon) {
            this.rowsWithResourceName[id] = { displayName: name };
        }
        return null;
    }

    /**
     * @override
     */
    shouldMergeGroups() {
        return false;
    }

    /**
     * Given a {start, end} datetime for a resource (row), return whether the resource is on day off.
     * This is determined by checking if the resource has any unavailabilities that intersect with the given column
     *
     * @param {Object} column - a {start, stop} datetime object for the resource's day
     * @param {Row} row - Row Object
     * @returns {boolean} - Whether the resource is on day off
     */
    _resourceOnDayoff(column, row) {
        const { unavailabilities } = row;
        const { start, stop } = column;

        return unavailabilities.some((unavailability) => {
            const unavailabilityStart = unavailability.start;
            const unavailabilityEnd = unavailability.stop ? unavailability.stop : null;
            return (
                compareDates(unavailabilityStart, start) <= 0 &&
                (!unavailabilityEnd || compareDates(unavailabilityEnd, stop) >= 0)
            );
        });
    }

    /**
     * Split a shift (pill) into two shifts.
     * For shifts with flexible hours or open slots, the split is done without taking into account availabbilities.
     * For shifts with regular working hours, the split is done taking into account the resource's availabilities.
     * As an exception, if the shift spans on weekends (where the resource had no availabilities unavailable)
     * for a regular working schedule, we split the shift but set a 8-17 schedule for the shift in weekends.
     *
     * @param {Pill} pill
     * @param {number} startColumnId - column where to split the pill
     */
    /** Where a shift splits at a column: at the resource's availability limits, or at the work day's. */
    splitBounds(pill, startColumnId) {
        const resourceId = pill.record.resource_id.id || false;
        const splitRightPill = this.getColumnStartStop(startColumnId, startColumnId);
        const splitLeftPill = this.getColumnStartStop(
            startColumnId - 1,
            startColumnId - 1,
        );
        if (!resourceId || this.isFlexibleHours(resourceId)) {
            return { start: splitRightPill.start, stop: splitLeftPill.stop };
        }
        const currentRow = this.getRowFromPill(pill);
        const start = this._resourceOnDayoff(splitRightPill, currentRow)
            ? splitRightPill.start.with({
                  hour: 8,
                  minute: 0,
                  second: 0,
                  millisecond: 0,
              })
            : this.getColumnAvailabilitiesLimit(pill, startColumnId, {
                  fixed_stop: pill.record.end_datetime,
              }).start;
        const stop = this._resourceOnDayoff(splitLeftPill, currentRow)
            ? splitLeftPill.stop.with({
                  hour: 17,
                  minute: 0,
                  second: 0,
                  millisecond: 0,
              })
            : this.getColumnAvailabilitiesLimit(pill, startColumnId - 1, {
                  fixed_start: pill.record.start_datetime,
              }).stop;
        return { start, stop };
    }

    async onPillSplitToolClicked(pill, startColumnId) {
        const { start, stop } = this.splitBounds(pill, startColumnId);
        const copiedShiftId = await this.model.splitPill(start, stop, pill.record);
        // Close the last split notification if any and show a new split notification with an Undo button
        this.closeNotificationFn?.();
        this.closeNotificationFn = this.notificationService.add(
            markup`<i class="fa-solid fa-check"></i><span class="ms-1">${_t(
                "Shift divided into two",
            )}</span>`,
            {
                type: "success",
                className: "planning_notification",
                buttons: [
                    {
                        name: "Undo",
                        icon: "fa-undo",
                        onClick: () => this.undoSplit(pill.record, copiedShiftId),
                    },
                ],
            },
        );
    }

    /** Merge the two halves of a split back, on the schedule the shift had before it. */
    async undoSplit(record, copiedShiftId) {
        const result = await this.model.orm.call(
            this.model.metaData.resModel,
            "undo_split_shift",
            [
                [record.id, copiedShiftId],
                serializeDateTime(record.start_datetime),
                serializeDateTime(record.end_datetime),
                !record.resource_id ? false : record.resource_id.id,
            ],
        );
        this.closeNotificationFn?.();
        if (!result) {
            this.closeNotificationFn = this.notificationService.add(
                markup`<i class="fa-solid fa-check"></i><span class="ms-1">${_t(
                    "Shifts could not be merged back",
                )}</span>`,
                { type: "danger" },
            );
        } else {
            this.model.fetchData();
            this.closeNotificationFn = this.notificationService.add(
                markup`<i class="fa-solid fa-check"></i><span class="ms-1">${_t(
                    "Shifts merged back",
                )}</span>`,
                { type: "success" },
            );
        }
    }

    getUndoAfterDragMessages(dragAction) {
        if (dragAction === "copy") {
            return {
                success: _t("Shift duplicated"),
                undo: _t("Shift removed"),
                failure: _t("Shift could not be removed"),
            };
        }
        return {
            success: _t("Shift rescheduled"),
            undo: _t("Shift reschedule undone"),
            failure: _t("Failed to undo reschedule"),
        };
    }

    getUndoAfterDragRecordData(record) {
        return {
            ...super.getUndoAfterDragRecordData(...arguments),
            recurrence_update: record.recurrence_update,
        };
    }

    /**
     * Determines the earliest (in start) and latest (in stop) availability in a column for the row of a given pill.
     * If a fixed start/stop is set, the latest/earliest availability as to be after/before it. If the row shows no
     * availability respecting the given constraint, the returned start/stop allows to create a shift of 1 second.
     *
     * @param {Pill} pill
     * @param {number} column - Column index
     * @param {{ Datetime, Datetime }} { fixed_start, fixed_stop } - If set, indicates a fixed value for the start/stop result
     * @returns {{ Datetime, Datetime }} { start, stop }
     */
    getColumnAvailabilitiesLimit(pill, column, { fixed_start, fixed_stop } = {}) {
        const defaultColumnTiming = super.getColumnStartStop(column, column);
        let start = fixed_start || defaultColumnTiming.start;
        let stop = fixed_stop || defaultColumnTiming.stop;
        const currentRow = this.getRowFromPill(pill);

        const unavailability_at_start = currentRow?.unavailabilities?.find(
            (unavailability) =>
                compareDates(start, unavailability.start) >= 0 &&
                Boolean(unavailability.stop) &&
                compareDates(start, unavailability.stop) < 0,
        );
        const unavailability_at_stop = currentRow?.unavailabilities?.find(
            (unavailability) =>
                compareDates(stop, unavailability.start) > 0 &&
                Boolean(unavailability.stop) &&
                compareDates(stop, unavailability.stop) <= 0,
        );

        if (!fixed_stop && unavailability_at_stop) {
            stop = unavailability_at_stop.start;
        }
        if (!fixed_start && unavailability_at_start && compareDates(stop, start) > 0) {
            start = unavailability_at_start.stop;
        }
        if (compareDates(stop, start) <= 0) {
            if (!fixed_start) {
                start = fromEpochMilliseconds(stop.epochMilliseconds - 1000);
            } else {
                stop = fromEpochMilliseconds(start.epochMilliseconds + 1000);
            }
        }
        return { start, stop };
    }

    get controlsProps() {
        return Object.assign(super.controlsProps, {
            duplicateToolHelperReactive: this.duplicateToolHelperReactive,
        });
    }

    onInteractionChange() {
        super.onInteractionChange();
        this.duplicateToolHelperReactive.shouldDisplay =
            this.interaction.mode === "drag";
    }

    async dragPillDrop({ pill }) {
        const { record } = this.pills[pill.dataset.pillId];
        if (record.repeat && this.interaction.dragAction !== "copy") {
            const recurrenceUpdate = await planningAskRecurrenceUpdate(
                this.dialogService,
            );
            if (recurrenceUpdate) {
                record.recurrence_update = recurrenceUpdate;
                super.dragPillDrop(...arguments);
            }
        } else {
            super.dragPillDrop(...arguments);
        }
    }

    async resizePillDrop({ pill }) {
        const { record } = this.pills[pill.dataset.pillId];
        if (record.repeat) {
            const recurrenceUpdate = await planningAskRecurrenceUpdate(
                this.dialogService,
            );
            if (recurrenceUpdate) {
                record.recurrence_update = recurrenceUpdate;
                super.resizePillDrop(...arguments);
            }
        } else {
            super.resizePillDrop(...arguments);
        }
    }
}
