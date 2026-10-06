/** @odoo-module native */
import { onWillUnmount } from "@odoo/owl";
import {
    compareDates,
    DATE_SHORT,
    DATETIME_SHORT,
    diff as dateDiff,
    endOf,
    getEndOfLocalWeek,
    getStartOfLocalWeek,
    hasSame,
    startOf,
    TIME_SIMPLE,
    toLocaleString,
} from "@web/core/l10n/dates";
import { pick, shallowEqual } from "@web/core/utils/collections/objects";
import { makeDraggableHook } from "@web/core/utils/dnd";
import { closest as getClosest } from "@web/core/utils/dom/ui";
import { clamp } from "@web/core/utils/format/numbers";
import { useIsDestroyed, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { makePopover, usePopover } from "@web/ui/popover";

import { GanttPopoverInDialog } from "./gantt_popover_in_dialog.js";

/**
 * @param {number} target
 * @param {number[]} values
 * @returns {number}
 */
function closest(target, values) {
    return values.reduce(
        (prev, val) => (Math.abs(val - target) < Math.abs(prev - target) ? val : prev),
        Infinity,
    );
}

/**
 * Adds a time diff to a date keeping the same value even if the offset changed
 * during the manipulation. This is typically needed with timezones using DayLight
 * Saving offset changes.
 *
 * @param {Temporal.ZonedDateTime} date
 * @param {Record<string, number>} plusParams
 */
export function dateAddFixedOffset(date, plusParams) {
    const shouldApplyOffset = Object.keys(plusParams).some((key) =>
        /^(hour|minute|second)s?$/i.test(key),
    );
    const result = addDuration(date, plusParams);
    if (shouldApplyOffset) {
        const initialOffset = date.offsetNanoseconds;
        const diff = initialOffset - result.offsetNanoseconds;
        if (diff) {
            const adjusted = result.add({ nanoseconds: diff });
            return adjusted.offsetNanoseconds === initialOffset ? result : adjusted;
        }
    }
    return result;
}

const MONTHS_PER_UNIT = { years: 12, quarters: 3, months: 1 };
const DAYS_PER_UNIT = { years: 365, quarters: 91, months: 30, weeks: 7, days: 1 };
const MILLISECONDS_PER_UNIT = {
    hours: 3_600_000,
    minutes: 60_000,
    seconds: 1000,
    milliseconds: 1,
};

/**
 * `date` plus `params`: singular or plural keys, signs mixed freely, the
 * whole calendar units first and the time units, with any fraction of a
 * calendar unit, as elapsed time after them -- where Temporal's own `add`
 * refuses singular keys, mixed signs and fractions.
 *
 * @param {Temporal.ZonedDateTime} date
 * @param {Record<string, number>} params
 * @returns {Temporal.ZonedDateTime}
 */
export function addDuration(date, params) {
    let months = 0;
    let days = 0;
    let milliseconds = 0;
    for (const [key, value] of Object.entries(params)) {
        const unit = key.endsWith("s") ? key : `${key}s`;
        if (unit in DAYS_PER_UNIT) {
            const whole = Math.trunc(value);
            if (unit in MONTHS_PER_UNIT) {
                months += whole * MONTHS_PER_UNIT[unit];
            } else {
                days += whole * DAYS_PER_UNIT[unit];
            }
            milliseconds += (value - whole) * DAYS_PER_UNIT[unit] * 86_400_000;
        } else if (unit in MILLISECONDS_PER_UNIT) {
            milliseconds += value * MILLISECONDS_PER_UNIT[unit];
        } else {
            throw new Error(`addDuration: unknown unit ${key}`);
        }
    }
    return date
        .add({ months })
        .add({ days })
        .add({ milliseconds: Math.round(milliseconds) });
}

/**
 * How many `unit`s separate `col1` from `col2`, fractional, counted as luxon
 * did (core `diff`): across a DST change that removes midnight, a day boundary
 * landing at 01:00 is still a whole number of days away.
 *
 * @param {Temporal.ZonedDateTime} col1
 * @param {Temporal.ZonedDateTime} col2
 * @param {string} unit
 * @returns {number}
 */
export function diffColumn(col1, col2, unit) {
    return dateDiff(col2, col1, /** @type {any} */ (`${unit}s`));
}

export function localStartOf(date, unit) {
    return unit === "week" ? getStartOfLocalWeek(date) : startOf(date, unit);
}

export function localEndOf(date, unit) {
    return unit === "week" ? getEndOfLocalWeek(date) : endOf(date, unit);
}

/**
 * @param {number} cellPart
 * @param {(0 | 1)[]} subSlotUnavailabilities
 * @param {boolean} isToday
 * @returns {string | null}
 */
export function getCellColor(cellPart, subSlotUnavailabilities, isToday) {
    const sum = subSlotUnavailabilities.reduce((acc, d) => acc + d, 0);
    if (!sum) {
        return null;
    }
    if (sum === cellPart) {
        // Every sub-slot is off: one flat colour, not a gradient of one stop.
        return `background-color:${getCellPartColor(1, isToday)}`;
    }
    const colors = subSlotUnavailabilities.map((d) => getCellPartColor(d, isToday));
    if (cellPart === 2) {
        const [c0, c1] = colors;
        return `background:linear-gradient(90deg,${c0}49%,${c1}50%)`;
    }
    const [c0, c1, c2, c3] = colors;
    return `background:linear-gradient(90deg,${c0}24%,${c1}25%,${c1}49%,${c2}50%,${c2}74%,${c3}75%)`;
}

/**
 * @param {0 | 1} availability
 * @param {boolean} isToday
 * @returns {string}
 */
export function getCellPartColor(availability, isToday) {
    if (availability) {
        return "var(--Gantt__DayOff-background-color)";
    } else if (isToday) {
        return "var(--Gantt__DayOffToday-background-color)";
    } else {
        return "var(--Gantt__Day-background-color)";
    }
}

/**
 * Intervals are supposed to intersect (intersection duration >= 1 milliseconds)
 *
 * @param {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} interval
 * @param {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} otherInterval
 * @returns {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]}
 */
export function getIntersection(interval, otherInterval) {
    const [start, end] = interval;
    const [otherStart, otherEnd] = otherInterval;
    return [
        compareDates(start, otherStart) >= 0 ? start : otherStart,
        compareDates(end, otherEnd) <= 0 ? end : otherEnd,
    ];
}

/**
 * Computes intersection of a closed interval with a union of closed intervals ordered and disjoint
 * = a union of intersections
 *
 * @param {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} interval
 * @param {[Temporal.ZonedDateTime, Temporal.ZonedDateTime][]} intervals
 * @returns {[Temporal.ZonedDateTime, Temporal.ZonedDateTime][]}
 */
export function getUnionOfIntersections(interval, intervals) {
    const [start, end] = interval;
    const intersecting = intervals.filter((otherInterval) => {
        const [otheStart, otherEnd] = otherInterval;
        return compareDates(otherEnd, start) > 0 && compareDates(end, otheStart) > 0;
    });
    const len = intersecting.length;
    if (len === 0) {
        return [];
    }
    const union = [];
    const first = getIntersection(interval, intersecting[0]);
    union.push(first);
    if (len >= 2) {
        const last = getIntersection(interval, intersecting[len - 1]);
        union.push(...intersecting.slice(1, len - 1), last);
    }
    return union;
}

export function getHoveredCellPart(cell, pointerX, cellPart, rtl) {
    const rect = cell.getBoundingClientRect();
    const x = Math.floor(rect.x);
    const width = Math.floor(rect.width);
    let part = Math.floor((clamp(pointerX, x, x + width - 1) - x) / (width / cellPart));
    part = clamp(part, 0, cellPart - 1);
    if (rtl) {
        part = cellPart - 1 - part;
    }
    return part;
}

export function getClosestCell(ctx, rowId) {
    const { hoveredCell, pointer, ref, rtl, scale } = ctx;
    let { el: cell, part } = hoveredCell;
    if (!cell) {
        const selector = rowId
            ? `.o_gantt_cells .o_gantt_cell:not(.o_drag_hover)[data-row-id='${CSS.escape(rowId)}']`
            : `.o_gantt_cells .o_gantt_cell:not(.o_drag_hover)`;
        // Nothing to be closest to when the row has no unfolded cell left.
        cell = getClosest(ref.el.querySelectorAll(selector), pointer) || null;
        part = cell ? getHoveredCellPart(cell, pointer.x, scale.cellPart, rtl) : 0;
    }
    return { cell, part };
}

/**
 * @param {Object} params
 * @param {Ref<HTMLElement>} params.ref
 * @param {string} params.selector
 * @param {string} params.exception
 * @param {string[]} params.related
 * @param {string} params.className
 */
export function useMultiHover({ ref, selector, exception, related, className }) {
    /**
     * @param {HTMLElement} el
     */
    const findSiblings = (el) =>
        ref.el.querySelectorAll(
            related
                .map((attr) => `[${attr}='${CSS.escape(el.getAttribute(attr))}']`)
                .join(""),
        );

    /**
     * @param {PointerEvent} ev
     */
    const onPointerEnter = (ev) => {
        if (!ev.target.classList.contains(exception)) {
            for (const sibling of findSiblings(ev.target)) {
                sibling.classList.add(...classList);
                classedEls.add(sibling);
            }
        }
    };

    /**
     * @param {PointerEvent} ev
     */
    const onPointerLeave = (ev) => {
        for (const sibling of findSiblings(ev.target)) {
            sibling.classList.remove(...classList);
            classedEls.delete(sibling);
        }
    };

    const classList = className.split(/\s+/g);
    const classedEls = new Set();

    useLayoutEffect(
        (...targets) => {
            if (targets.length) {
                for (const target of targets) {
                    target.addEventListener("pointerenter", onPointerEnter);
                    target.addEventListener("pointerleave", onPointerLeave);
                }
                return () => {
                    for (const el of classedEls) {
                        el.classList.remove(...classList);
                    }
                    classedEls.clear();
                    for (const target of targets) {
                        target.removeEventListener("pointerenter", onPointerEnter);
                        target.removeEventListener("pointerleave", onPointerLeave);
                    }
                };
            }
        },
        () => [...ref.el.querySelectorAll(selector)],
    );
}

function getElementCenter(el) {
    const { x, y, width, height } = el.getBoundingClientRect();
    return {
        x: x + width / 2,
        y: y + height / 2,
    };
}

function getBadgesPositions(el, rtl) {
    const rect = el.getBoundingClientRect();
    const sideBarWidth =
        el.closest(".o_gantt_renderer")?.querySelector(".o_gantt_row_sidebar")
            ?.offsetWidth || 0;
    const startPosition = {
        left: Math.max(rect.x, sideBarWidth),
        top: rect.top - 20,
    };
    const stopPosition = {
        top: rect.y + rect.height,
        right: clamp(
            document.body.offsetWidth - rect.x - rect.width,
            1,
            window.innerWidth - sideBarWidth,
        ),
    };
    return {
        startPosition: rtl ? stopPosition : startPosition,
        stopPosition: rtl ? startPosition : stopPosition,
    };
}

function getBadgeText(date, diff, scale, withDate = false) {
    const { cellPart, time, unitDescription } = scale;
    let text;
    switch (time) {
        case "minute":
            // A time alone reads wrong once the drag crosses midnight.
            text = toLocaleString(date, withDate ? DATETIME_SHORT : TIME_SIMPLE);
            break;
        case "hour":
            text =
                cellPart > 1
                    ? toLocaleString(date, DATETIME_SHORT)
                    : toLocaleString(date, DATE_SHORT);
            break;
        default:
            text = toLocaleString(date, DATE_SHORT);
    }
    if (diff) {
        const prefix = diff > 0 ? "+" : "";
        text += ` (${prefix}${diff} ${unitDescription})`;
    }
    return text;
}

function getBadge(position, text, diff) {
    return {
        class: diff ? (diff > 0 ? "text-success" : "text-danger") : "",
        position,
        text,
    };
}

export function getBadges(
    el,
    [startDate, startDiff],
    [stopDate, stopDiff],
    { rtl, scale },
    showDiff = true,
) {
    const { startPosition, stopPosition } = getBadgesPositions(el, rtl);
    const withDate = !hasSame(startDate, stopDate, "day");
    const startBadge = getBadge(
        startPosition,
        getBadgeText(startDate, showDiff ? startDiff : 0, scale, withDate),
        startDiff,
    );
    const stopBadge = getBadge(
        stopPosition,
        getBadgeText(stopDate, showDiff ? stopDiff : 0, scale, withDate),
        stopDiff,
    );
    return { startBadge, stopBadge };
}

// Resizable hook handles

const HANDLE_CLASS_START = "o_handle_start";
const HANDLE_CLASS_END = "o_handle_end";

// Draggable hooks

export const useGanttConnectorDraggable = makeDraggableHook({
    name: "useGanttConnectorDraggable",
    acceptedParams: {
        parentWrapper: [String],
    },
    onComputeParams({ ctx, params }) {
        ctx.parentWrapper = params.parentWrapper;
        ctx.followCursor = false;
    },
    onDragStart: ({ ctx, addStyle }) => {
        const { current } = ctx;
        const parent = current.element.closest(ctx.parentWrapper);
        if (!parent) {
            return;
        }
        for (const otherParent of ctx.ref.el.querySelectorAll(ctx.parentWrapper)) {
            if (otherParent !== parent) {
                addStyle(otherParent, { pointerEvents: "auto" });
            }
        }
        return { sourcePill: parent, ...current.connectorCenter };
    },
    onDrag: ({ ctx }) => {
        ctx.current.connectorCenter = getElementCenter(ctx.current.element);
        return pick(ctx.current, "connectorCenter");
    },
    onDragEnd: ({ ctx }) => pick(ctx.current, "element"),
    onDrop: ({ ctx, target }) => {
        const { current } = ctx;
        const parent = current.element.closest(ctx.parentWrapper);
        const targetParent = target.closest(ctx.parentWrapper);
        if (!targetParent || targetParent === parent) {
            return;
        }
        return { target: targetParent };
    },
    onWillStartDrag: ({ ctx }) => {
        ctx.current.connectorCenter = getElementCenter(ctx.current.element);
        return {};
    },
});

function getCoordinate(style, name) {
    return +style.getPropertyValue(name).slice(1);
}

export function getColumnStart(style) {
    return getCoordinate(style, "grid-column-start");
}

export function getColumnEnd(style) {
    return getCoordinate(style, "grid-column-end");
}

function getRowStart(style) {
    return getCoordinate(style, "grid-row-start");
}

function getRowEnd(style) {
    return getCoordinate(style, "grid-row-end");
}

export const useGanttDraggable = makeDraggableHook({
    name: "useGanttDraggable",
    acceptedParams: {
        cells: [String, Function],
        cellDragClassName: [String, Function],
        ghostClassName: [String, Function],
        hoveredCell: [Object],
        addStickyCoordinates: [Function],
        rtl: [Boolean, Function],
        scale: [Object, Function],
        getBadgesInitialDates: [Function],
    },
    onComputeParams({ ctx, params }) {
        ctx.cellSelector = params.cells;
        ctx.ghostClassName = params.ghostClassName;
        ctx.cellDragClassName = params.cellDragClassName;
        ctx.hoveredCell = params.hoveredCell;
        ctx.addStickyCoordinates = params.addStickyCoordinates;
        ctx.scale = params.scale;
        ctx.getBadgesInitialDates = params.getBadgesInitialDates;
        ctx.rtl = params.rtl;
    },
    onDragStart({ ctx }) {
        const { current, ghostClassName } = ctx;
        current.element.before(current.placeHolder);
        if (ghostClassName) {
            current.placeHolder.classList.add(ghostClassName);
        }
        return { pill: current.element };
    },
    onDrag({ ctx, addStyle }) {
        const { cellSelector, current, getBadgesInitialDates, hoveredCell, scale } =
            ctx;
        let { el: cell, part } = hoveredCell;

        const isDifferentCell = cell !== current.cell.el;
        const isDifferentPart = part !== current.cell.part;

        if (cell && !cell.matches(cellSelector)) {
            cell = null; // Not a cell
        }
        if (cell && cell.classList.contains("o_gantt_cell_folded")) {
            return;
        }

        current.cell.el = cell;
        current.cell.part = part;

        if (cell) {
            // Recompute cell style if in a different cell
            if (isDifferentCell) {
                const style = getComputedStyle(cell);
                current.cell.gridRow = style.getPropertyValue("grid-row");
                current.cell.gridColumnStart =
                    getColumnStart(style) + current.gridColumnOffset;
            }
            // Assign new grid coordinates if in different cell or different cell part
            if (isDifferentCell || isDifferentPart) {
                const { pillSpan } = current;
                const { gridRow, gridColumnStart: start } = current.cell;
                const gridColumnStart = clamp(
                    start + part,
                    1,
                    current.maxGridColumnStart,
                );
                const gridColumnEnd = gridColumnStart + pillSpan;
                current.diff = gridColumnStart - current.initialCol;

                addStyle(current.cellGhost, {
                    gridRow,
                    gridColumn: `c${gridColumnStart} / c${gridColumnEnd}`,
                });

                const [gridRowStart, gridRowEnd] = /r(\d+) \/ r(\d+)/g
                    .exec(gridRow)
                    .slice(1);
                ctx.addStickyCoordinates(
                    [gridRowStart, gridRowEnd],
                    [gridColumnStart, gridColumnEnd],
                );
                current.cell.col = gridColumnStart;
            }
        } else {
            current.cell.col = null;
        }

        // Attach or remove cell ghost
        if (isDifferentCell) {
            if (cell) {
                cell.after(current.cellGhost);
            } else {
                current.cellGhost.remove();
            }
        }
        const { cellTime, time } = scale;
        const { start, stop } = getBadgesInitialDates();
        const diff = current.diff * cellTime;
        const startDate = dateAddFixedOffset(start, { [time]: diff });
        const stopDate = dateAddFixedOffset(stop, { [time]: diff });
        return getBadges(
            current.element,
            [startDate, diff],
            [stopDate, diff],
            ctx,
            false,
        );
    },
    onDragEnd({ ctx }) {
        return { pill: ctx.current.element };
    },
    onDrop({ ctx }) {
        const { cellSrc, cell, element, initialCol } = ctx.current;
        if (cell.col !== null) {
            return {
                pill: element,
                cellSrc: cellSrc,
                cellDst: cell.el,
                diff: cell.col - initialCol,
            };
        }
    },
    onWillStartDrag({ ctx, addCleanup, addClass }) {
        const { current } = ctx;
        const { el: cell, part } = ctx.hoveredCell;

        current.placeHolder = current.element.cloneNode(true);
        current.cellGhost = document.createElement("div");
        current.cellGhost.className = ctx.cellDragClassName;
        current.cell = { el: null, index: null, part: 0 };
        current.cellSrc = cell;

        const gridStyle = getComputedStyle(cell.parentElement);
        const pillStyle = getComputedStyle(current.element);
        const cellStyle = getComputedStyle(cell);

        const gridTemplateColumns = gridStyle.getPropertyValue("grid-template-columns");
        const pGridColumnStart = getColumnStart(pillStyle);
        const pGridColumnEnd = getColumnEnd(pillStyle);
        const cGridColumnStart = getColumnStart(cellStyle) + part;

        let highestGridCol;
        for (const e of gridTemplateColumns.split(/\s+/).reverse()) {
            const res = /\[c(\d+)\]/g.exec(e);
            if (res) {
                highestGridCol = +res[1];
                break;
            }
        }

        const pillSpan = pGridColumnEnd - pGridColumnStart;

        current.initialCol = pGridColumnStart;
        current.diff = 0;
        current.maxGridColumnStart = highestGridCol - pillSpan;
        current.gridColumnOffset = pGridColumnStart - cGridColumnStart;
        current.pillSpan = pillSpan;

        addClass(ctx.ref.el, "pe-auto");
        addCleanup(() => {
            current.placeHolder.remove();
            current.cellGhost.remove();
        });
        return {};
    },
});

export const useGanttUndraggable = makeDraggableHook({
    name: "useGanttUndraggable",
    onDragStart({ ctx }) {
        return { pill: ctx.current.element };
    },
    onDragEnd({ ctx }) {
        return { pill: ctx.current.element };
    },
    onWillStartDrag({ ctx, addCleanup, addClass, addStyle, getRect }) {
        const { x, y, width, height } = getRect(ctx.current.element);
        ctx.current.container = document.createElement("div");

        addClass(ctx.ref.el, "pe-auto");
        addStyle(ctx.current.container, {
            position: "fixed",
            left: `${x}px`,
            top: `${y}px`,
            width: `${width}px`,
            height: `${height}px`,
        });

        ctx.current.element.after(ctx.current.container);
        addCleanup(() => ctx.current.container.remove());
        return {};
    },
});

export const useGanttResizable = makeDraggableHook({
    name: "useGanttResizable",
    requiredParams: ["handles"],
    acceptedParams: {
        innerPills: [String, Function],
        handles: [String, Function],
        hoveredCell: [Object],
        rtl: [Boolean, Function],
        cells: [String, Function],
        scale: [Object, Function],
        getBadgesInitialDates: [Function],
        showHandles: [Function],
    },
    onComputeParams({ ctx, params, addCleanup, addEffectCleanup, getRect }) {
        // Scoped to this hook instance so two simultaneously-mounted gantt
        // views don't fight over the same DOM nodes.
        const handles = {
            start: document.createElement("div"),
            end: document.createElement("div"),
        };

        /** Pill currently showing the handles, or null. */
        let handlesPill = null;

        const showHandlesOn = (pill) => {
            const innerPill = pill.querySelector(params.innerPills);
            if (!innerPill) {
                return;
            }

            const pillRect = getRect(innerPill);

            for (const el of Object.values(handles)) {
                el.style.height = `${pillRect.height}px`;
            }

            const showHandles = params.showHandles ? params.showHandles(pill) : {};
            if ("start" in showHandles && !showHandles.start) {
                handles.start.remove();
            } else {
                innerPill.appendChild(handles.start);
            }
            if ("end" in showHandles && !showHandles.end) {
                handles.end.remove();
            } else {
                innerPill.appendChild(handles.end);
            }
            handlesPill = pill;
        };

        const hideHandles = () => {
            handlesPill = null;
            const remove = () => Object.values(handles).forEach((h) => h.remove());
            if (ctx.dragging || ctx.current.element) {
                addCleanup(remove);
            } else {
                remove();
            }
        };

        // Delegated on the grid instead of bound per pill. This effect is keyed on
        // param VALUES, so it does not re-run when a re-render replaces the pills —
        // and it can even run while none exist yet: switching the gantt range bound
        // zero elements and never rebound, so hovering a pill afterwards showed no
        // resize handles at all.
        const onGridPointerOver = (ev) => {
            if (ctx.dragging || ctx.willDrag) {
                return;
            }
            const pill = ev.target.closest?.(params.elements);
            if (!pill || pill === handlesPill) {
                return;
            }
            showHandlesOn(pill);
        };

        // ``pointerout`` also fires when moving onto a descendant (a handle is a
        // child of the pill), hence the containment check.
        const onGridPointerOut = (ev) => {
            if (!handlesPill || ev.target.closest?.(params.elements) !== handlesPill) {
                return;
            }
            if (ev.relatedTarget && handlesPill.contains(ev.relatedTarget)) {
                return;
            }
            hideHandles();
        };

        ctx.hoveredCell = params.hoveredCell;
        ctx.scale = params.scale;
        ctx.getBadgesInitialDates = params.getBadgesInitialDates;
        ctx.rtl = params.rtl;

        const grid = ctx.ref.el;
        grid.addEventListener("pointerover", onGridPointerOver);
        grid.addEventListener("pointerout", onGridPointerOut);
        addEffectCleanup(() => {
            grid.removeEventListener("pointerover", onGridPointerOver);
            grid.removeEventListener("pointerout", onGridPointerOut);
        });

        handles.start.className = `${params.handles} ${HANDLE_CLASS_START}`;
        handles.start.style.cursor = `${params.rtl ? "e" : "w"}-resize`;

        handles.end.className = `${params.handles} ${HANDLE_CLASS_END}`;
        handles.end.style.cursor = `${params.rtl ? "w" : "e"}-resize`;

        // Override "full" and "element" selectors: we want the draggable feature
        // to apply to the handles
        ctx.pillSelector = ctx.elementSelector;
        ctx.fullSelector = ctx.elementSelector = `.${params.handles}`;

        // Force the handles to stay in place
        ctx.followCursor = false;
    },
    onDragStart({ ctx, addStyle }) {
        addStyle(ctx.current.pill, { zIndex: 15 });
        return { pill: ctx.current.pill };
    },
    onDrag({ ctx, addStyle, getRect }) {
        const { getBadgesInitialDates, current, scale, pointer, rtl } = ctx;
        const { cell, part } = getClosestCell(ctx, ctx.current.rowId);
        if (!cell || cell.classList.contains("o_gantt_cell_folded")) {
            return;
        }
        const cellStyle = getComputedStyle(cell);
        const cGridColStart = getColumnStart(cellStyle);

        const { x, width } = getRect(cell);
        const coef = ((rtl ? -1 : 1) * width) / scale.cellPart;
        const startBorder = (rtl ? x + width : x) + part * coef;
        const endBorder = startBorder + coef;

        const theClosest = closest(pointer.x, [startBorder, endBorder]);

        let diff =
            cGridColStart +
            part +
            (theClosest === startBorder ? 0 : 1) -
            (current.isStart ? current.firstCol : current.lastCol);

        if (diff === current.lastDiff) {
            return;
        }

        if (current.isStart) {
            diff = Math.min(diff, current.initialDiff - 1);
            addStyle(current.pill, {
                "grid-column-start": `c${current.firstCol + diff}`,
            });
        } else {
            diff = Math.max(diff, 1 - current.initialDiff);
            addStyle(current.pill, { "grid-column-end": `c${current.lastCol + diff}` });
        }
        current.lastDiff = diff;

        const { cellTime, time } = scale;
        const startDiff = current.isStart ? -diff * cellTime : 0;
        const stopDiff = current.isStart ? 0 : diff * cellTime;
        const { start, stop } = getBadgesInitialDates();
        const startDate = current.isStart
            ? dateAddFixedOffset(start, {
                  [time]: diff * cellTime,
              })
            : start;
        const stopDate = current.isStart
            ? stop
            : dateAddFixedOffset(stop, {
                  [time]: diff * cellTime,
              });
        return getBadges(
            current.pill,
            [startDate, startDiff],
            [stopDate, stopDiff],
            ctx,
        );
    },
    onDragEnd({ ctx }) {
        const { current, pillSelector } = ctx;
        const pill = current.element.closest(pillSelector);
        return { pill };
    },
    onDrop({ ctx }) {
        const { current } = ctx;

        if (!current.lastDiff) {
            return;
        }

        const direction = current.isStart ? "start" : "end";
        return { pill: current.pill, diff: current.lastDiff, direction };
    },
    onWillStartDrag({ ctx, addClass }) {
        const { current, hoveredCell, pillSelector } = ctx;

        const pill = ctx.current.element.closest(pillSelector);
        current.pill = pill;

        const pillStyle = getComputedStyle(pill);
        current.firstCol = getColumnStart(pillStyle);
        current.lastCol = getColumnEnd(pillStyle);
        current.initialDiff = current.lastCol - current.firstCol;

        const { el: cell } = hoveredCell;
        current.rowId = cell.dataset.rowId;

        ctx.cursor = getComputedStyle(current.element).cursor;

        current.isStart = current.element.classList.contains(HANDLE_CLASS_START);

        addClass(ctx.ref.el, "pe-auto");
        return {};
    },
});

function getCellBounds({ cell, part }) {
    const startCol = +cell.dataset.col + part;
    const endCol = startCol + 1;
    const style = getComputedStyle(cell);
    const startRow = getRowStart(style);
    const endRow = getRowEnd(style);
    return { startCol, endCol, startRow, endRow };
}

function getBlockBounds(current) {
    const startCol = Math.min(
        current.initialCellBounds.startCol,
        current.cellBounds.startCol,
    );
    const endCol = Math.max(
        current.initialCellBounds.endCol,
        current.cellBounds.endCol,
    );
    const startRow = current.rowId
        ? current.initialCellBounds.startRow
        : Math.min(current.initialCellBounds.startRow, current.cellBounds.startRow);
    const endRow = current.rowId
        ? current.initialCellBounds.endRow
        : Math.max(current.initialCellBounds.endRow, current.cellBounds.endRow);
    return { startCol, endCol, startRow, endRow };
}

function getResult(current) {
    return { ...getBlockBounds(current), rowId: current.rowId };
}

/**
 * @param {HTMLElement} refEl: gantt grid
 * @param {string} rowId
 * @param {string} additionalSelector
 * @returns {NodeListOf<HTMLElement>} cells found on the row that matched the selector
 */
export function getCellsOnRow(refEl, rowId, additionalSelector = "") {
    return refEl.querySelectorAll(
        `.o_gantt_cell${additionalSelector}[data-row-id='${CSS.escape(rowId)}']`,
    );
}

export const useGanttSelectable = makeDraggableHook({
    name: "useGanttSelectable",
    acceptedParams: {
        hoveredCell: [Object],
        hasMultiCreate: [Boolean, Function],
        rtl: [Boolean, Function],
        scale: [Object, Function],
    },
    onComputeParams({ ctx, params }) {
        ctx.followCursor = false;
        ctx.hoveredCell = params.hoveredCell;
        ctx.hasMultiCreate = params.hasMultiCreate;
        ctx.rtl = params.rtl;
        ctx.scale = params.scale;
    },
    onWillStartDrag({ addClass, ctx }) {
        const { current, hoveredCell, ref } = ctx;
        const { el: cell, part } = hoveredCell;
        const cellBounds = getCellBounds({ cell, part });
        current.initialCellBounds = cellBounds;
        current.cellBounds = cellBounds;
        current.rowId = ctx.hasMultiCreate ? null : cell.dataset.rowId;
        addClass(ref.el, "pe-auto");
        addClass(cell, "pe-auto");
        return getResult(current);
    },
    onDragStart({ ctx, removeClass }) {
        const { current } = ctx;
        // Useless on cells, annoying on pills
        removeClass(current.element, "o_dragged");
        return getResult(current);
    },
    onDrag({ ctx }) {
        const { current } = ctx;
        const { cell, part } = getClosestCell(ctx, current.rowId);
        if (!cell || cell.classList.contains("o_gantt_cell_folded")) {
            return;
        }
        const cellBounds = getCellBounds({ cell, part });
        if (shallowEqual(current.cellBounds, cellBounds)) {
            return;
        }
        current.cellBounds = cellBounds;
        return getResult(current);
    },
    onDrop({ ctx }) {
        const { current } = ctx;
        return getResult(current);
    },
    onDragEnd() {
        // Needed in order to be used in hook caller
        return {};
    },
});

/**
 * Same as usePopover, but replaces the popover by a dialog when display size is small.
 *
 * @param {string} dialogTitle
 * @param {typeof import("@odoo/owl").Component} component
 * @param {import("@web/ui/popover").PopoverServiceAddOptions} [options]
 * @returns {import("@web/ui/popover").PopoverHookReturnType}
 */
export function useGanttResponsivePopover(dialogTitle, component, options = {}) {
    const dialogService = useService("dialog");
    const ui = useService("ui");
    const env = {
        get isSmall() {
            return ui.isSmall;
        },
    };
    const isDestroyed = useIsDestroyed();
    const popover = usePopover(component, options);
    const onClose = () => {
        if (!isDestroyed()) {
            options.onClose?.();
        }
    };
    const dialogAddFn = (_, comp, props, options) =>
        dialogService.add(comp, props, options);
    const popoverInDialog = makePopover(dialogAddFn, GanttPopoverInDialog, { onClose });
    const ganttResponsivePopover = {
        open: (target, props) => {
            if (env.isSmall) {
                popoverInDialog.open(target, {
                    component: component,
                    componentProps: props,
                    dialogTitle,
                });
            } else {
                popover.open(target, props);
            }
        },
        close: () => {
            popover.close();
            popoverInDialog.close();
        },
        get isOpen() {
            return popover.isOpen || popoverInDialog.isOpen;
        },
    };
    onWillUnmount(ganttResponsivePopover.close);
    return ganttResponsivePopover;
}
