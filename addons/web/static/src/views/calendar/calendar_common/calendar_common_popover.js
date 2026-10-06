// @ts-check
/** @odoo-module native */

import { Component, t, useListener, useProps } from "@odoo/owl";
import { dateSettings, diff, formatValue, hasSame } from "@web/core/l10n/dates";
import { is24HourFormat } from "@web/core/l10n/time";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Field } from "@web/fields/field";
import { Record } from "@web/model/record";
import { Dialog } from "@web/ui/dialog/dialog";
import { getColor, getFormattedDateSpan } from "@web/views/calendar/calendar_utils";

/**
 * A duration's count as the calendar has always shown it: rounded down, in the
 * user's numbering system.
 *
 * @param {number} value
 * @returns {string}
 */
function formatDurationCount(value) {
    const count = Math.floor(value);
    const numberingSystem = dateSettings.numberingSystem;
    if (!numberingSystem || numberingSystem === "latn") {
        return String(count);
    }
    return new Intl.NumberFormat(dateSettings.locale, {
        useGrouping: false,
        numberingSystem,
    }).format(count);
}

export class CalendarCommonPopover extends Component {
    static template = "web.CalendarCommonPopover";
    static subTemplates = {
        popover: "web.CalendarCommonPopover.popover",
        body: "web.CalendarCommonPopover.body",
        footer: "web.CalendarCommonPopover.footer",
    };
    static components = {
        Dialog,
        Field,
        Record,
    };
    static props = {
        close: t.function(),
        record: t.object(),
        model: t.object(),
        createRecord: t.function(),
        deleteRecord: t.function(),
        editRecord: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.time = null;
        this.timeDuration = null;
        this.date = null;
        this.dateDuration = null;

        useListener(
            window,
            "pointerdown",
            (e) => {
                const target = /** @type {HTMLElement} */ (e.target);
                const onCalendar = target.closest(".o_calendar_widget, .fc-popover");
                const onSourceEvent = target.closest(
                    `.fc-event[data-event-id="${this.props.record.id}"]`,
                );
                if (onCalendar && !onSourceEvent) {
                    e.preventDefault();
                }
            },
            { capture: true },
        );

        this.computeDateTimeAndDuration();
    }

    get activeFields() {
        return this.props.model.activeFields;
    }
    get isEventEditable() {
        return this.props.model.canEdit;
    }
    get isEventDeletable() {
        return this.props.model.canDelete;
    }
    get isEventViewable() {
        return true;
    }
    get hasFooter() {
        return this.isEventEditable || this.isEventDeletable || this.isEventViewable;
    }
    get colorClass() {
        const color = getColor(this.props.record.colorIndex);
        return `o_calendar_color_${typeof color === "number" ? color : 0}`;
    }

    /**
     * @param {{ [key: string]: any }} fieldNode
     * @param {{ [key: string]: any }} record
     * @returns {boolean}
     */
    isInvisible(fieldNode, record) {
        return evaluateBooleanExpr(
            fieldNode.invisible,
            record.evalContextWithVirtualIds,
        );
    }

    /**
     * @param {string} fieldName
     * @param {{ [key: string]: any }} record
     * @returns {string}
     */
    getFormattedValue(fieldName, record) {
        const fieldInfo = this.props.model.popoverFieldNodes[fieldName];
        const field = this.props.model.fields[fieldName];
        let format;
        const formattersRegistry = registry.category("formatters");
        if (fieldInfo.widget && formattersRegistry.contains(fieldInfo.widget)) {
            format = formattersRegistry.get(fieldInfo.widget);
        } else {
            format = formattersRegistry.get(field.type);
        }
        // a selection resolves its label from the field, a monetary its currency
        // from the record
        return format(record.data[fieldName], { field, data: record.data });
    }

    computeDateTimeAndDuration() {
        const record = this.props.record;
        const { start, end } = record;
        const isSameDay = Boolean(end) && hasSame(start, end, "day");

        if (!record.isTimeHidden && !record.isAllDay && isSameDay) {
            const timeFormat = is24HourFormat() ? "HH:mm" : "hh:mm a";
            this.time = `${formatValue(start, timeFormat)} - ${formatValue(end, timeFormat)}`;

            const milliseconds = end.epochMilliseconds - start.epochMilliseconds;
            const hours = Math.trunc(milliseconds / 3600000);
            const minutes = (milliseconds - hours * 3600000) / 60000;
            const formatParts = [];
            if (hours > 0) {
                const hourString = hours === 1 ? _t("hour") : _t("hours");
                formatParts.push(`${formatDurationCount(hours)} ${hourString}`);
            }
            if (minutes > 0) {
                const minuteStr = minutes === 1 ? _t("minute") : _t("minutes");
                formatParts.push(`${formatDurationCount(minutes)} ${minuteStr}`);
            }
            this.timeDuration = formatParts.length
                ? formatParts.join(", ")
                : _t("0 minutes");
        }

        if (!this.props.model.isDateHidden) {
            this.date = getFormattedDateSpan(start, end);

            if (record.isAllDay) {
                if (isSameDay) {
                    this.dateDuration = _t("All day");
                } else if (end) {
                    const days = diff(end.add({ days: 1 }), start, "days");
                    this.dateDuration = `${formatDurationCount(days)} ${_t("days")}`;
                }
            }
        }
    }

    onEditEvent() {
        this.props.editRecord(this.props.record);
        this.props.close();
    }
    onDeleteEvent() {
        this.props.deleteRecord(this.props.record);
        this.props.close();
    }
}
