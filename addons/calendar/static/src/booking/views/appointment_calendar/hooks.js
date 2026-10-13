/** @odoo-module native */
import { useAppointmentCalendarContext } from "@calendar/booking/views/appointment_calendar/appointment_calendar_context";
import { proxy } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export function useAppointmentRendererHook(component, getFcElements) {
    const env = {
        calendarState: useAppointmentCalendarContext().calendarState,
    };
    proxy(env.calendarState);

    useLayoutEffect(
        (fcEls, calendarMode) => {
            if (calendarMode === "slots-creation") {
                for (const fcEl of fcEls) {
                    const daysToDisable = fcEl.querySelectorAll(
                        ".fc-day-past:not(.fc-col-header-cell), .fc-day-today:not(.fc-col-header-cell)",
                    );
                    fcEl.classList.add("o_calendar_slots_in_creation");
                    for (const el of daysToDisable) {
                        el.classList.add("o_calendar_slot_selection");
                    }
                    const todayColumn = fcEl.querySelectorAll(
                        ".fc-day-today:not(.fc-col-header-cell)",
                    )[1];
                    const bgColumn = todayColumn?.querySelector(".fc-timegrid-col-bg");
                    const nowIndicator = todayColumn?.querySelector(
                        ".fc-timegrid-now-indicator-line",
                    );
                    if (
                        bgColumn &&
                        nowIndicator &&
                        ["timeGridWeek", "timeGridDay"].includes(
                            component.fc.api.view.type,
                        )
                    ) {
                        const height = nowIndicator.style.top.slice(0, -2);
                        const childEl = document.createElement("div");
                        childEl.classList.add(
                            "o_calendar_slot_selection_now",
                            "position-absolute",
                            "start-0",
                            "end-0",
                        );
                        childEl.style.height = `${height}px`;
                        bgColumn.appendChild(childEl);
                    }
                }
                return () => {
                    for (const fcEl of fcEls) {
                        const daysToDisable = fcEl.querySelectorAll(
                            ".fc-day-past:not(.fc-col-header-cell), .fc-day-today:not(.fc-col-header-cell)",
                        );
                        fcEl.classList.remove("o_calendar_slots_in_creation");
                        for (const el of daysToDisable) {
                            el.classList.remove("o_calendar_slot_selection");
                        }
                        const todayColumn = fcEl.querySelectorAll(
                            ".fc-day-today:not(.fc-col-header-cell)",
                        )[1];
                        if (todayColumn) {
                            const childEl = todayColumn.querySelector(
                                ".o_calendar_slot_selection_now",
                            );
                            childEl && childEl.remove();
                        }
                    }
                };
            }
        },
        () => [getFcElements(), env.calendarState.mode],
    );
    return {
        isSlotCreationMode() {
            return env.calendarState.mode === "slots-creation";
        },

        getEventTimeFormat() {
            const format12Hour = {
                hour: "numeric",
                minute: "2-digit",
                omitZeroMinute: true,
                meridiem: "short",
            };
            const format24Hour = {
                hour: "numeric",
                minute: "2-digit",
                hour12: false,
            };
            return localization.timeFormat.search("HH") === 0
                ? format24Hour
                : format12Hour;
        },
    };
}

/**
 * @param {Component} component
 * @param {unknown[]} superSources
 */
export function eventSourcesWithSlots(component, superSources) {
    return [...superSources, component.props.model.data.slots];
}

/**
 * @param {Component} component
 * @param {Object} record
 */
export function convertSlotToEvent(component, record) {
    const result = {
        ...component.convertRecordToEvent(record),
        id: component.maxResId + record.id,
        slotId: record.id,
    };
    result.editable = true;
    return result;
}

/**
 * @param {Component} component
 * @param {Array} superEvents
 */
export function mapRecordsAndSlotsToEvents(component, superEvents) {
    component.maxResId = Math.max(
        0,
        ...Object.keys(component.props.model.data.records).map((id) =>
            Number.parseInt(id),
        ),
    );
    return [
        ...superEvents,
        ...Object.values(component.props.model.data.slots).map((r) =>
            convertSlotToEvent(component, r),
        ),
    ];
}

/**
 * @param {Object} event
 * @param {Object} superRecord
 */
export function fcEventToRecordWithSlot(event, superRecord) {
    return {
        ...superRecord,
        slotId: event.extendedProps.slotId,
    };
}
