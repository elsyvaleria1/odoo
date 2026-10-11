/** @odoo-module native */
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import {
    compareDates,
    dateSettings,
    endOf,
    formatValue,
    hasSame,
    maxDate,
    now,
    startOf,
    TIME_SIMPLE,
    toISO,
    toISODate,
    toJSDate,
    toLocaleString,
} from "@web/core/l10n/dates";
import { scrollTo } from "@web/core/utils/dom/scrolling";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export function makeInterval(start, end) {
    return { start, end };
}

function intervalContains(interval, value) {
    return (
        compareDates(interval.start, value) <= 0 &&
        compareDates(value, interval.end) < 0
    );
}

function intervalsOverlap(a, b) {
    return compareDates(a.end, b.start) > 0 && compareDates(a.start, b.end) < 0;
}

function splitInterval(interval, unit, amount) {
    const pieces = [];
    let start = interval.start;
    for (let index = 1; compareDates(start, interval.end) < 0; index++) {
        const added = interval.start.add({ [unit]: amount * index });
        const next = compareDates(added, interval.end) > 0 ? interval.end : added;
        pieces.push(makeInterval(start, next));
        start = next;
    }
    return pieces;
}

function formatHoursMinutes(from, to) {
    const minutes = Math.floor((to.epochMilliseconds - from.epochMilliseconds) / 60000);
    return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

export class RoomBookingForm extends Component {
    static template = "room.RoomBookingForm";
    static props = {
        createBooking: t.function(),
        bookings: t.array(),
        bookingToEdit: t.object().optional(),
        cancel: t.function(),
        editBooking: t.function(),
        bookingName: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.root = elementRef();
        this.state = proxy({
            selectedDay: this.props.bookingToEdit
                ? maxDate(
                      this.props.bookingToEdit.interval.start.startOfDay(),
                      this.today,
                  )
                : this.today,
            bookingStart: this.props.bookingToEdit
                ? maxDate(this.props.bookingToEdit.interval.start, now())
                : undefined,
            bookingEnd: this.props.bookingToEdit?.interval.end,
            bookingName: this.props.bookingToEdit?.name || this.props.bookingName,
        });

        onWillUpdateProps((nextProps) => {
            if (nextProps.bookingToEdit !== this.props.bookingToEdit) {
                this.state.selectedDay = maxDate(
                    nextProps.bookingToEdit.interval.start.startOfDay(),
                    this.today,
                );
                this.state.bookingStart = maxDate(
                    nextProps.bookingToEdit.interval.start,
                    now(),
                );
                this.state.bookingEnd = nextProps.bookingToEdit.interval.end;
                this.state.bookingName = nextProps.bookingToEdit.name;
            }
        });

        useLayoutEffect(
            () => {
                const slot = this.root.el.querySelector(
                    `#slot${
                        this.state.bookingStart
                            ?.startOfDay()
                            .equals(this.state.selectedDay)
                            ? formatValue(this.state.bookingStart, "HHmm")
                            : "0800"
                    }`,
                );
                if (slot) {
                    scrollTo(slot, { isAnchor: true });
                }
            },
            () => [this.state.selectedDay],
        );
    }

    get dayFormat() {
        return { weekday: "short", day: "numeric" };
    }

    get monthFormat() {
        return { year: "numeric", month: "long" };
    }

    get timeFormat() {
        return TIME_SIMPLE;
    }

    format(value, format) {
        return formatValue(value, format);
    }

    formatLocalized(value, options) {
        return toLocaleString(value, options);
    }

    isBeforeToday(value) {
        return compareDates(this.today, value) > 0;
    }

    slotKey(slot) {
        return toISO(slot.start);
    }

    get bookingsByDate() {
        return this.props.bookings.reduce((bookingsByDate, booking) => {
            if (this.props.bookingToEdit?.id === booking.id) {
                return bookingsByDate;
            }
            const intervals = [];
            let { start, end } = booking.interval;
            if (start.startOfDay().equals(end.startOfDay())) {
                intervals.push(booking.interval);
            } else {
                while (compareDates(start.startOfDay(), end.startOfDay()) < 0) {
                    const nextDay = start.add({ days: 1 }).startOfDay();
                    intervals.push(makeInterval(start, nextDay));
                    start = nextDay;
                }
                intervals.push(makeInterval(start, end));
            }
            for (const interval of intervals) {
                const date = toISODate(interval.start);
                if (!(date in bookingsByDate)) {
                    bookingsByDate[date] = [];
                }
                bookingsByDate[date].push(interval);
            }
            return bookingsByDate;
        }, {});
    }

    get formattedMonth() {
        const { start, end } = this.weekInterval;
        return new Intl.DateTimeFormat(dateSettings.locale, {
            ...this.monthFormat,
            timeZone: start.timeZoneId,
            numberingSystem: dateSettings.numberingSystem,
        }).formatRange(toJSDate(start), toJSDate(end));
    }

    get slots() {
        const intervals = [];
        const isToday = this.state.selectedDay.equals(this.today);
        if (isToday) {
            let firstSlotTime = now();
            if (
                this.state.bookingStart &&
                compareDates(this.state.bookingStart, firstSlotTime) < 0
            ) {
                firstSlotTime = this.state.bookingStart;
            }
            intervals.push(
                makeInterval(
                    firstSlotTime,
                    startOf(
                        firstSlotTime.add({
                            minutes: 30 - (firstSlotTime.minute % 30),
                        }),
                        "minute",
                    ),
                ),
            );
        }
        const remainingInterval = makeInterval(
            intervals[0]?.end || this.state.selectedDay,
            this.state.selectedDay.add({ days: 1 }),
        );
        intervals.push(...splitInterval(remainingInterval, "minutes", 30));

        const bookings = this.bookingsByDate[toISODate(this.state.selectedDay)] || [];
        let bookingIdx = 0;
        let isBooked = false;
        let isInSelectedInterval = false;
        let canBeEndDate = false;
        if (
            this.props.bookingToEdit &&
            compareDates(
                this.props.bookingToEdit.interval.start,
                this.state.selectedDay,
            ) < 0 &&
            compareDates(
                this.props.bookingToEdit.interval.end,
                this.state.selectedDay,
            ) > 0
        ) {
            isInSelectedInterval = true;
            canBeEndDate = true;
        }
        const slots = [];
        for (const interval of intervals) {
            const slot = {
                start: interval.start,
                isInSelectedInterval,
                canBeEndDate,
            };
            if (
                this.state.bookingEnd &&
                intervalContains(interval, this.state.bookingEnd)
            ) {
                isInSelectedInterval = false;
            } else if (
                this.state.bookingStart &&
                intervalContains(interval, this.state.bookingStart)
            ) {
                slot.isInSelectedInterval = true;
                canBeEndDate = true;
                isInSelectedInterval = Boolean(this.state.bookingEnd);
            } else if (canBeEndDate && !isInSelectedInterval) {
                slot.description = formatHoursMinutes(
                    this.state.bookingStart,
                    interval.start,
                );
            }
            if (
                bookings[bookingIdx] &&
                intervalsOverlap(bookings[bookingIdx], interval) &&
                !isBooked
            ) {
                isBooked = true;
                canBeEndDate = false;
            }
            slot.isBooked = isBooked;
            if (isBooked && compareDates(interval.end, bookings[bookingIdx].end) >= 0) {
                isBooked = false;
                bookingIdx++;
            }
            slots.push(slot);
        }
        if (this.state.bookingStart && canBeEndDate) {
            const midnight = this.state.selectedDay.add({ days: 1 });
            const isEnd = this.state.bookingEnd?.equals(midnight);
            slots.push({
                start: midnight,
                canBeEndDate,
                isInSelectedInterval: isEnd,
                description: isEnd
                    ? false
                    : formatHoursMinutes(this.state.bookingStart, midnight),
            });
        }
        return slots;
    }

    get today() {
        return now().startOfDay();
    }

    get weekInterval() {
        return makeInterval(
            startOf(this.state.selectedDay, "week"),
            endOf(this.state.selectedDay, "week"),
        );
    }

    get weekIntervalDays() {
        return splitInterval(this.weekInterval, "days", 1);
    }

    confirm() {
        if (this.props.bookingToEdit) {
            this.props.editBooking(
                this.props.bookingToEdit.id,
                this.state.bookingName,
                compareDates(this.props.bookingToEdit.interval.start, now()) < 0 &&
                    compareDates(this.state.bookingStart, now()) < 0
                    ? this.props.bookingToEdit.interval.start
                    : this.state.bookingStart,
                this.state.bookingEnd,
            );
        } else {
            this.props.createBooking(
                this.state.bookingName,
                this.state.bookingStart,
                this.state.bookingEnd,
            );
        }
    }

    onNextWeekClick() {
        this.state.selectedDay = this.state.selectedDay.add({ weeks: 1 });
    }

    onPreviousWeekClick() {
        const day = this.state.selectedDay.subtract({ weeks: 1 });
        this.state.selectedDay = compareDates(day, this.today) < 0 ? this.today : day;
    }

    /**
     * Handle a click on a slot.
     * @param {Object} slot
     * @param {Temporal.ZonedDateTime} slot.start
     * @param {Boolean} slot.canBeEndDate
     * @param {Boolean} slot.isBooked
     */
    onSlotClick(slot) {
        if (!this.state.bookingStart) {
            if (!slot.isBooked) {
                this.state.bookingStart = slot.start;
            }
        } else {
            if (slot.start.equals(this.state.bookingStart)) {
                this.state.bookingStart = null;
                this.state.bookingEnd = null;
            } else if (slot.canBeEndDate) {
                if (this.state.bookingEnd && slot.start.equals(this.state.bookingEnd)) {
                    this.state.bookingEnd = null;
                } else {
                    this.state.bookingEnd = slot.start;
                }
            } else if (!slot.isBooked) {
                if (
                    !hasSame(slot.start, this.state.bookingStart, "day") ||
                    compareDates(slot.start, this.state.bookingStart) > 0 ||
                    this.bookingsByDate[toISODate(this.state.selectedDay)]?.some(
                        (booking) =>
                            intervalsOverlap(
                                booking,
                                makeInterval(slot.start, this.state.bookingStart),
                            ),
                    )
                ) {
                    this.state.bookingEnd = null;
                }
                this.state.bookingStart = slot.start;
            }
        }
    }
}
