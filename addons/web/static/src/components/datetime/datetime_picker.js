// @ts-check
/** @odoo-module native */

import {
    Component,
    onMounted,
    onWillUnmount,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { TimePicker } from "@web/components/time_picker/time_picker";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { dateSettings } from "@web/core/l10n/date_settings";
import {
    areDatesEqual,
    clampDate,
    compareDates,
    diff,
    endOf,
    formatDuration,
    getMaxValidDate,
    getMinValidDate,
    getStartOfLocalWeek,
    isDateValue,
    isInRange,
    monthNames,
    now,
    resolveZone,
    startOf,
    toDate,
    toDateTime,
    today as currentDay,
    toISO,
    toISODate,
    toLocaleString,
    weekdayNames,
} from "@web/core/l10n/dates";
import { Time } from "@web/core/l10n/time";
import { _t } from "@web/core/translation";
import { ensureArray } from "@web/core/utils/collections/arrays";

/**
 * @typedef DateItem
 * @property {string} id
 * @property {boolean} includesToday
 * @property {boolean} isOutOfRange
 * @property {boolean} isValid
 * @property {string} label
 * @property {DateRange} range
 * @property {string} extraClass
 * @typedef {"today" | NullableDateValue} DateLimit
 * @typedef {Temporal.ZonedDateTime | Temporal.PlainDate} DateTime a day of the
 *  grid, and a value: a date for a "date" picker, a datetime otherwise
 * @typedef {[DateTime, DateTime]} DateRange
 * @typedef DateTimePickerProps
 * @property {number} [focusedDateIndex=0]
 * @property {boolean} [showWeekNumbers=true]
 * @property {DaysOfWeekFormat} [daysOfWeekFormat="narrow"]
 * @property {DateLimit} [maxDate]
 * @property {PrecisionLevel} [maxPrecision="decades"]
 * @property {DateLimit} [minDate]
 * @property {PrecisionLevel} [minPrecision="days"]
 * @property {() => any} [onReset]
 * @property {(value: NullableDateValue | NullableDateValue[], unit: SelectionUnit, focusedDateIndex?: number) => any} [onSelect]
 * @property {() => any} [onToggleRange]
 * @property {(index: number) => any} [onBoundSelect]
 * @property {boolean} [range]
 * @property {[string, string]} [boundLabels]
 * @property {number} [monthCount=1]
 * @property {boolean} [showPresets]
 * @property {KeyboardPort} [keyboard]
 * @property {number} [rounding=5]
 * @property {string} [tz]
 * @property {boolean} [showRangeToggler]
 * @property {{ buttons?: any }} [slots]
 * @property {"date" | "datetime"} [type]
 * @property {NullableDateValue | NullableDateValue[]} [value]
 * @property {(date: DateTime) => boolean} [isDateValid]
 * @property {(date: DateTime) => string} [dayCellClass]
 * @typedef {DateItem | MonthItem} Item
 * @typedef MonthItem
 * @property {[string, string, string][]} daysOfWeek
 * @property {string} id
 * @property {number} number
 * @property {WeekItem[]} weeks
 * @typedef {import("@web/core/l10n/dates").NullableDateTime} NullableDateTime
 * @typedef {import("@web/core/l10n/dates").NullableDateRange} NullableDateRange
 * @typedef {import("@web/core/l10n/dates").NullableDateValue} NullableDateValue
 * @typedef PrecisionInfo
 * @property {(date: DateTime, params?: Partial<DateTimePickerProps>) => string | string[]} getTitle
 * @property {(date: DateTime, params: Partial<DateTimePickerProps> & { now: DateTime }) => Item[]} getItems
 * @property {string} mainTitle
 * @property {string} nextTitle
 * @property {string} prevTitle
 * @property {Temporal.DurationLike} step
 * @property {KeySteps} keySteps
 * @typedef {"days" | "months" | "years" | "decades"} PrecisionLevel
 * @typedef {"date" | "time" | "range"} SelectionUnit
 * @typedef KeyboardPort where the picker's owner hands it the keys typed in
 *  the owner's inputs; the handler answers whether it used the key
 * @property {((ev: KeyboardEvent) => boolean) | null} handler
 * @typedef KeySteps
 * @property {Temporal.DurationLike} across
 * @property {Temporal.DurationLike} down
 * @property {Temporal.DurationLike} page
 * @property {Temporal.DurationLike} bigPage
 * @typedef RangePreset
 * @property {string} id
 * @property {string} label
 * @property {NullableDateValue[]} value
 * @property {boolean} isActive
 * @property {boolean} isValid
 * @typedef {"short" | "narrow"} DaysOfWeekFormat
 * @typedef WeekItem
 * @property {DateItem[]} days
 * @property {number} number
 */

const log = makeLogger("web.components.datetime_picker");

/**
 * How long a range lasts; a date range counts both its days, and a range
 * ending on a day's last minute runs through that day
 *
 * @param {DateTime} start
 * @param {DateTime} end
 * @param {"date" | "datetime"} [type="datetime"]
 * @param {boolean} [full=true] two units spelled out, or the largest one abbreviated
 * @returns {string}
 */
export function formatRangeDuration(start, end, type = "datetime", full = true) {
    if (type === "date") {
        const days = diff(toDate(end), toDate(start), "days");
        return formatDuration((Math.round(days) + Math.sign(days || 1)) * 86400, full);
    }
    const startTime = toDateTime(start);
    const endTime = toDateTime(end);
    const through =
        endTime.hour === 23 && endTime.minute === 59 ? endOf(endTime, "day") : endTime;
    return formatDuration(
        Math.round((through.epochMilliseconds - startTime.epochMilliseconds) / 1000),
        full,
    );
}

/** @param {DateTime} date */
const getStartOfDecade = (date) => Math.floor(date.year / 10) * 10;

/** @param {DateTime} date */
const getStartOfCentury = (date) => Math.floor(date.year / 100) * 100;

/**
 * @param {number} min
 * @param {number} max
 */
const numberRange = (min, max) => [...Array(max - min)].map((_, i) => i + min);

/**
 * The same wall time as `value`, in `zone`
 *
 * @param {Temporal.ZonedDateTime} value
 * @param {string} zone
 * @returns {Temporal.ZonedDateTime}
 */
const keepWallTimeIn = (value, zone) => value.toPlainDateTime().toZonedDateTime(zone);

/**
 * A length spelled out in the user's locale: "2 weeks"
 *
 * @param {Partial<Record<"months" | "weeks" | "days" | "hours", number>>} length
 * @returns {string}
 */
const humanizeLength = (length) => {
    const { locale, numberingSystem } = dateSettings;
    const parts = Object.entries(length).map(([unit, value]) =>
        new Intl.NumberFormat(locale, {
            useGrouping: false,
            style: "unit",
            unitDisplay: "long",
            unit: unit.slice(0, -1),
            numberingSystem,
        }).format(/** @type {number} */ (value)),
    );
    return new Intl.ListFormat(locale, { type: "conjunction", style: "narrow" }).format(
        parts,
    );
};

/**
 * @param {Temporal.ZonedDateTime} date
 * @param {number} rounding minutes per step; 0 or less steps by the second
 * @param {boolean} up
 * @returns {Temporal.ZonedDateTime}
 */
const alignToStep = (date, rounding, up) => {
    const unit = rounding > 0 ? "minute" : "second";
    let aligned = startOf(date, unit);
    if (up && !aligned.equals(date)) {
        aligned = aligned.add({ [`${unit}s`]: 1 });
    }
    if (rounding <= 1) {
        return aligned;
    }
    const minute = (up ? Math.ceil : Math.floor)(aligned.minute / rounding) * rounding;
    return minute >= 60
        ? startOf(aligned, "hour").add({ hours: 1 })
        : aligned.with({ minute });
};

/**
 * A limit of a date picker is a day; one of a datetime picker is an instant,
 * and a day given to it covers the whole of that day in `zone`
 *
 * @param {DateLimit | undefined} value
 * @param {"min" | "max"} boundary
 * @param {DateTime} today
 * @param {"date" | "datetime"} type
 * @param {string} zone
 * @returns {DateTime}
 */
const parseLimitDate = (value, boundary, today, type, zone) => {
    const [minValid, maxValid] = [getMinValidDate(), getMaxValidDate()];
    /** @type {DateTime} */
    let limit =
        value === "today" ? today : value || (boundary === "min" ? minValid : maxValid);
    if (type === "date") {
        return clampDate(toDate(limit), toDate(minValid), toDate(maxValid));
    }
    if (isDateValue(limit)) {
        limit = toDateTime(limit, zone);
        if (boundary === "max") {
            limit = endOf(limit, "day");
        }
    }
    return clampDate(limit, minValid, maxValid);
};

/**
 * @param {Object} params
 * @param {boolean} [params.isOutOfRange=false]
 * @param {boolean} [params.isValid=true]
 * @param {string} params.label
 * @param {string} [params.extraClass]
 * @param {[DateTime, DateTime]} params.range
 * @param {DateTime} params.now
 * @returns {DateItem}
 */
const toDateItem = ({
    isOutOfRange = false,
    isValid = true,
    label,
    range,
    now,
    extraClass = "",
}) => ({
    id: toISODate(range[0]),
    includesToday: isInRange(now, range),
    isOutOfRange,
    isValid,
    label,
    range,
    extraClass,
});

/**
 * @param {DateItem[]} weekDayItems
 * @returns {WeekItem}
 */
const toWeekItem = (weekDayItems) => ({
    number: /** @type {number} */ (weekDayItems[3].range[0].weekOfYear),
    days: weekDayItems,
});

/**
 * @param {DateTime} date
 * @param {number} offset
 * @param {{ maxDate: DateTime, minDate: DateTime, now: DateTime, showWeekNumbers?: boolean }} params
 * @returns {MonthItem}
 */
function getMonthItem(date, offset, { maxDate, minDate, now, showWeekNumbers }) {
    /** @type {DateRange} */
    const monthRange = [startOf(date, "month"), endOf(date, "month")];
    /** @type {WeekItem[]} */
    const weeks = [];

    let startOfNextWeek = getStartOfLocalWeek(monthRange[0]);
    for (let w = 0; w < WEEKS_PER_MONTH; w++) {
        const weekDayItems = [];
        for (let d = 0; d < DAYS_PER_WEEK; d++) {
            const day = startOfNextWeek.add({ days: d });
            /** @type {DateRange} */
            const range = [day, endOf(day, "day")];
            const dayItem = toDateItem({
                isOutOfRange: !isInRange(day, monthRange),
                isValid: isInRange(range, [minDate, maxDate]),
                label: String(day.day),
                range,
                now,
            });
            weekDayItems.push(dayItem);
            if (d === DAYS_PER_WEEK - 1) {
                startOfNextWeek = day.add({ days: 1 });
            }
        }

        weeks.push(toWeekItem(weekDayItems));
    }

    const shortWeekdays = weekdayNames("short");
    const longWeekdays = weekdayNames("long");
    const narrowWeekdays = weekdayNames("narrow");
    const daysOfWeek = weeks[0].days.map(
        (d) =>
            /** @type {[string, string, string]} */ ([
                shortWeekdays[d.range[0].dayOfWeek - 1],
                longWeekdays[d.range[0].dayOfWeek - 1],
                narrowWeekdays[d.range[0].dayOfWeek - 1],
            ]),
    );
    if (showWeekNumbers) {
        daysOfWeek.unshift(["", _t("Week numbers"), ""]);
    }

    return {
        id: `__month__${offset}`,
        number: monthRange[0].month,
        daysOfWeek,
        weeks,
    };
}

/** @type {Map<PrecisionLevel, PrecisionInfo>} */
const PRECISION_LEVELS = new Map()
    .set("days", {
        mainTitle: _t("Select month"),
        nextTitle: _t("Next month"),
        prevTitle: _t("Previous month"),
        step: { months: 1 },
        keySteps: {
            across: { days: 1 },
            down: { days: 7 },
            page: { months: 1 },
            bigPage: { years: 1 },
        },
        getTitle: (date, { monthCount = 1 } = {}) => {
            const monthTitle = (/** @type {DateTime} */ month) =>
                `${monthNames("long")[month.month - 1]} ${month.year}`;
            return monthCount > 1
                ? [monthTitle(date), monthTitle(date.add({ months: monthCount - 1 }))]
                : monthTitle(date);
        },
        getItems: (date, { monthCount = 1, ...params }) =>
            numberRange(0, monthCount).map((offset) =>
                getMonthItem(
                    date.add({ months: offset }),
                    offset,
                    /** @type {Parameters<typeof getMonthItem>[2]} */ (params),
                ),
            ),
    })
    .set("months", {
        mainTitle: _t("Select year"),
        nextTitle: _t("Next year"),
        prevTitle: _t("Previous year"),
        step: { years: 1 },
        keySteps: {
            across: { months: 1 },
            down: { months: 4 },
            page: { years: 1 },
            bigPage: { years: 10 },
        },
        getTitle: (date) => String(date.year),
        getItems: (date, { maxDate, minDate, now }) => {
            const startOfYear = startOf(date, "year");
            const shortMonths = monthNames("short");
            return numberRange(0, 12).map((i) => {
                const startOfMonth = startOfYear.add({ months: i });
                /** @type {DateRange} */
                const range = [startOfMonth, endOf(startOfMonth, "month")];
                return toDateItem({
                    isValid: isInRange(range, [minDate, maxDate]),
                    label: shortMonths[startOfMonth.month - 1],
                    range,
                    now,
                });
            });
        },
    })
    .set("years", {
        mainTitle: _t("Select decade"),
        nextTitle: _t("Next decade"),
        prevTitle: _t("Previous decade"),
        step: { years: 10 },
        keySteps: {
            across: { years: 1 },
            down: { years: 4 },
            page: { years: 10 },
            bigPage: { years: 100 },
        },
        getTitle: (date) =>
            `${getStartOfDecade(date) - 1} - ${getStartOfDecade(date) + 10}`,
        getItems: (date, { maxDate, minDate, now }) => {
            const startOfDecade = startOf(date, "year").with({
                year: getStartOfDecade(date),
            });
            return numberRange(-GRID_MARGIN, GRID_COUNT + GRID_MARGIN).map((i) => {
                const startOfYear = startOfDecade.add({ years: i });
                /** @type {DateRange} */
                const range = [startOfYear, endOf(startOfYear, "year")];
                return toDateItem({
                    isOutOfRange: i < 0 || i >= GRID_COUNT,
                    isValid: isInRange(range, [minDate, maxDate]),
                    label: String(startOfYear.year),
                    range,
                    now,
                });
            });
        },
    })
    .set("decades", {
        mainTitle: _t("Select century"),
        nextTitle: _t("Next century"),
        prevTitle: _t("Previous century"),
        step: { years: 100 },
        keySteps: {
            across: { years: 10 },
            down: { years: 40 },
            page: { years: 100 },
            bigPage: { years: 1000 },
        },
        getTitle: (date) =>
            `${getStartOfCentury(date) - 10} - ${getStartOfCentury(date) + 100}`,
        getItems: (date, { maxDate, minDate, now }) => {
            const startOfCentury = startOf(date, "year").with({
                year: getStartOfCentury(date),
            });
            return numberRange(-GRID_MARGIN, GRID_COUNT + GRID_MARGIN).map((i) => {
                const startOfDecade = startOfCentury.add({ years: i * 10 });
                /** @type {DateRange} */
                const range = [
                    startOfDecade,
                    endOf(startOfDecade.add({ years: 9 }), "year"),
                ];
                return toDateItem({
                    label: String(startOfDecade.year),
                    isOutOfRange: i < 0 || i >= GRID_COUNT,
                    isValid: isInRange(range, [minDate, maxDate]),
                    range,
                    now,
                });
            });
        },
    });

const GRID_COUNT = 10;
const GRID_MARGIN = 1;
const NULLABLE_DATETIME_PROPERTY = t.or([
    t.instanceOf(Temporal.ZonedDateTime),
    t.instanceOf(Temporal.PlainDate),
    t.literal(false),
    t.literal(null),
]);

const DAYS_PER_WEEK = 7;
const WEEKS_PER_MONTH = 6;

/** @extends {Component<DateTimePickerProps>} */
export class DateTimePicker extends Component {
    static props = {
        focusedDateIndex: t.number().optional(0),
        showWeekNumbers: t.boolean().optional(true),
        daysOfWeekFormat: t.string().optional("narrow"),
        maxDate: t.or([NULLABLE_DATETIME_PROPERTY, t.literal("today")]).optional(),
        maxPrecision: t
            .any() /* [...PRECISION_LEVELS.keys()].map((value) => ({ value })) */
            .optional("decades"),
        minDate: t.or([NULLABLE_DATETIME_PROPERTY, t.literal("today")]).optional(),
        minPrecision: t
            .any() /* [...PRECISION_LEVELS.keys()].map((value) => ({ value })) */
            .optional("days"),
        onReset: t.function().optional(),
        onSelect: t.function().optional(),
        onToggleRange: t.function().optional(),
        onBoundSelect: t.function().optional(),
        range: t.boolean().optional(),
        boundLabels: t.array(t.string()).optional(),
        monthCount: t.number().optional(1),
        showPresets: t.boolean().optional(false),
        keyboard: t.object().optional(),
        rounding: t.number().optional(5),
        tz: t.string().optional(),
        showRangeToggler: t.boolean().optional(),
        slots: t.object({ buttons: t.object().optional() }).optional(),
        type: t.or([t.literal("date"), t.literal("datetime")]).optional("datetime"),
        value: t
            .or([NULLABLE_DATETIME_PROPERTY, t.array(NULLABLE_DATETIME_PROPERTY)])
            .optional(),
        isDateValid: t.function().optional(),
        dayCellClass: t.function().optional(),
    };

    static template = "web.DateTimePicker";
    static components = { TimePicker };
    props = useProps(this.constructor.props);

    /** @type {NullableDateValue[]} */
    values;
    isDate = false;
    /** @type {DateTime} */
    maxDate;
    /** @type {DateTime} */
    minDate;
    /** @type {string} */
    zone;

    get activePrecisionLevel() {
        return PRECISION_LEVELS.get(this.state.precision);
    }

    get isLastPrecisionLevel() {
        return this.allowedPrecisionLevels.at(-1) === this.state.precision;
    }

    get titles() {
        return ensureArray(this.title);
    }

    /** @returns {DateTime} */
    get today() {
        return this.isDate ? currentDay(this.zone) : now(this.zone).startOfDay();
    }

    /** Months side by side: several only while a range is picked */
    get monthCount() {
        return this.props.range ? Math.max(1, this.props.monthCount) : 1;
    }

    get showBounds() {
        return Boolean(this.props.range && this.props.boundLabels);
    }

    setup() {
        useLifecycleLog(log);
        /** @type {PrecisionLevel[]} */
        this.allowedPrecisionLevels = [];
        /** @type {{ key?: any[], title?: string | string[], grid?: Item[] }} */
        this.gridMemo = {};
        this.shouldAdjustFocusDate = false;

        this.state = proxy({
            /** @type {DateTime | null} */
            focusDate: null,
            /** @type {DateTime | null} */
            hoveredDate: null,
            /** @type {Time[]} */
            timeValues: [],
            /** @type {PrecisionLevel} */
            precision: this.props.minPrecision,
            /**
             * The day the arrow keys move, while they drive the grid
             *
             * @type {DateTime | null}
             */
            cursorDate: null,
        });

        const onKeydown = (/** @type {KeyboardEvent} */ ev) => this.onKeydown(ev);
        onMounted(() => {
            if (this.props.keyboard) {
                this.props.keyboard.handler = onKeydown;
            }
        });
        onWillUnmount(() => {
            if (this.props.keyboard?.handler === onKeydown) {
                this.props.keyboard.handler = null;
            }
        });

        this.onPropsUpdated(this.props);
        onWillUpdateProps((nextProps) => this.onPropsUpdated(nextProps));
    }

    /** @param {DateTimePickerProps} props */
    onPropsUpdated(props) {
        const previousValues = this.values;
        this.zone = resolveZone(props.tz);
        this.isDate = props.type === "date";
        this.values = ensureArray(props.value).map((value) =>
            this.toPickerValue(value),
        );
        this.allowedPrecisionLevels = this.filterPrecisionLevels(
            props.minPrecision,
            props.maxPrecision,
        );

        const today = this.today;
        this.shouldAdjustFocusDate = !props.range && this.hasValueMoved(previousValues);
        let todayInGrid = today;
        if (!this.isDate) {
            const gridZone = /** @type {Temporal.ZonedDateTime} */ (
                    this.getDateToFocus(this.values, props.focusedDateIndex) ||
                    this.state.focusDate ||
                    today
            ).timeZoneId;
            todayInGrid = keepWallTimeIn(
                /** @type {Temporal.ZonedDateTime} */ (today),
                gridZone,
            );
            if ([props.minDate, props.maxDate].includes("today")) {
                log.logic("todayLimit", () => ({
                    tz: props.tz,
                    zone: this.zone,
                    gridZone,
                    today: toISO(today),
                    todayInGrid: toISO(todayInGrid),
                }));
            }
        }
        this.maxDate = parseLimitDate(
            props.maxDate,
            "max",
            todayInGrid,
            props.type,
            this.zone,
        );
        this.minDate = parseLimitDate(
            props.minDate,
            "min",
            todayInGrid,
            props.type,
            this.zone,
        );

        if (compareDates(this.maxDate, this.minDate) < 0) {
            console.error(
                `DateTimePicker: given "maxDate" (${toISO(this.maxDate)}) comes before ` +
                    `"minDate" (${toISO(this.minDate)}); no date can be selected.`,
            );
        }

        this.state.timeValues = this.getTimeValues(props);
        this.adjustFocus(this.values, props.focusedDateIndex, today);
    }

    /**
     * A value in the kind this picker picks: a date picker shows the day a
     * datetime falls on, a datetime picker the start of a date's day
     *
     * @param {NullableDateValue | undefined} value
     * @returns {NullableDateValue}
     */
    toPickerValue(value) {
        if (!value) {
            return value ?? false;
        }
        if (this.isDate) {
            return toDate(value);
        }
        return isDateValue(value) ? toDateTime(value, this.zone) : value;
    }

    /**
     * @param {NullableDateValue[]} [previousValues]
     * @returns {boolean}
     */
    hasValueMoved(previousValues) {
        if (!previousValues || previousValues.length !== this.values.length) {
            return true;
        }
        return !areDatesEqual(this.values, previousValues);
    }

    /** @returns {{ title: string | string[], grid: Item[] }} */
    get gridState() {
        const { showWeekNumbers } = this.props;
        const { focusDate } = this.state;
        const precision = this.activePrecisionLevel;
        const today = this.today;
        const now =
            focusDate && !isDateValue(focusDate) && !isDateValue(today)
                ? keepWallTimeIn(today, focusDate.timeZoneId)
                : today;
        const monthCount = this.monthCount;
        const key = [
            focusDate && toISO(focusDate),
            precision,
            monthCount,
            this.minDate && toISO(this.minDate),
            this.maxDate && toISO(this.maxDate),
            showWeekNumbers,
            toISO(now),
        ];
        const memo = this.gridMemo;
        if (!memo.key || key.some((value, index) => value !== memo.key?.[index])) {
            log.logic("rebuildGrid", () => ({
                precision: this.state.precision,
                focusDate: focusDate && toISODate(focusDate),
                tz: this.props.tz,
                gridZone:
                    focusDate && !isDateValue(focusDate) ? focusDate.timeZoneId : null,
                today: toISO(today),
                todayInGrid: toISO(now),
            }));
            memo.key = key;
            memo.title = precision.getTitle(focusDate, { monthCount });
            memo.grid = precision.getItems(focusDate, {
                maxDate: this.maxDate,
                minDate: this.minDate,
                monthCount,
                now,
                showWeekNumbers,
            });
        }
        return { title: memo.title ?? "", grid: memo.grid ?? [] };
    }

    get title() {
        return this.gridState.title;
    }

    /** @returns {Item[]} */
    get items() {
        return this.decorateGrid(this.gridState.grid);
    }

    /**
     * The values, previewing the range a click on the hovered day would make
     *
     * @returns {NullableDateValue[]}
     */
    get selectedRange() {
        const { focusedDateIndex, range } = this.props;
        const { hoveredDate } = this.state;
        const selectedRange = [...this.values];
        if (!range || !hoveredDate) {
            return selectedRange;
        }
        const [start, end] = this.values;
        if (focusedDateIndex === 0) {
            if (
                end &&
                (!start || compareDates(hoveredDate, startOf(start, "day")) < 0)
            ) {
                selectedRange[0] = hoveredDate;
            }
        } else if (!start || compareDates(hoveredDate, startOf(start, "day")) >= 0) {
            selectedRange[1] = hoveredDate;
        } else {
            selectedRange[0] = hoveredDate;
        }
        return selectedRange;
    }

    /** @returns {{ label: string, isInverted: boolean }} */
    get duration() {
        const [start, end] = this.values;
        if (!this.props.range || !start || !end) {
            return { label: "", isInverted: false };
        }
        return {
            label: formatRangeDuration(start, end, this.props.type),
            isInverted: compareDates(end, start) < 0,
        };
    }

    /** @returns {{ anchors: RangePreset[], lengths: RangePreset[] }} */
    get presets() {
        if (!this.props.range || !this.props.showPresets) {
            return { anchors: [], lengths: [] };
        }
        const today = this.today;
        const startOfWeek = getStartOfLocalWeek(today);
        const startOfMonth = startOf(today, "month");
        /** @type {[string, string, DateTime, DateTime][]} */
        const anchors = [
            ["today", _t("Today"), today, today],
            [
                "tomorrow",
                _t("Tomorrow"),
                today.add({ days: 1 }),
                today.add({ days: 1 }),
            ],
            ["this_week", _t("This week"), startOfWeek, startOfWeek.add({ days: 6 })],
            [
                "next_week",
                _t("Next week"),
                startOfWeek.add({ days: 7 }),
                startOfWeek.add({ days: 13 }),
            ],
            [
                "this_month",
                _t("This month"),
                startOfMonth,
                startOf(endOf(startOfMonth, "month"), "day"),
            ],
            [
                "next_month",
                _t("Next month"),
                startOfMonth.add({ months: 1 }),
                startOf(endOf(startOfMonth.add({ months: 1 }), "month"), "day"),
            ],
        ];
        const [start] = this.values;
        /** @type {Partial<Record<"months" | "weeks" | "days" | "hours", number>>[]} */
        const lengths = start
            ? [
                  ...(this.props.type === "datetime"
                      ? [{ hours: 1 }, { hours: 4 }]
                      : []),
                  { days: 1 },
                  { weeks: 1 },
                  { weeks: 2 },
                  { months: 1 },
              ]
            : [];
        return {
            anchors: anchors.map(([id, label, first, last]) =>
                this.toPreset(id, label, [
                    this.atBoundTime(first, 0),
                    this.atBoundTime(last, 1),
                ]),
            ),
            lengths: lengths.map((length) => {
                const duration = Temporal.Duration.from(length);
                const end =
                    this.props.type === "date"
                        ? /** @type {DateTime} */ (start)
                              .add(duration)
                              .subtract({ days: 1 })
                        : /** @type {DateTime} */ (start).add(duration);
                return this.toPreset(
                    `length_${duration.toString()}`,
                    humanizeLength(length),
                    [start, end],
                );
            }),
        };
    }

    /**
     * @param {string} id
     * @param {string} label
     * @param {NullableDateValue[]} value
     * @returns {RangePreset}
     */
    toPreset(id, label, value) {
        const [start, end] = value;
        if (
            start &&
            end &&
            compareDates(end, start) <= 0 &&
            this.props.type === "datetime"
        ) {
            value = [start, start.add({ hours: 1 })];
        }
        return {
            id,
            label,
            value,
            isActive: areDatesEqual(value, this.values),
            isValid: value.every(
                (bound) => bound && isInRange(bound, [this.minDate, this.maxDate]),
            ),
        };
    }

    /**
     * A preset keeps the time a bound already has; an empty bound covers the
     * whole of its day
     *
     * @param {DateTime} day
     * @param {number} valueIndex
     * @returns {DateTime}
     */
    atBoundTime(day, valueIndex) {
        if (this.props.type !== "datetime") {
            return day;
        }
        const bound = this.values[valueIndex];
        if (!bound) {
            return valueIndex
                ? startOf(endOf(day, "day"), "minute")
                : startOf(day, "day");
        }
        const { hour, minute, second } = /** @type {Temporal.ZonedDateTime} */ (bound);
        return /** @type {Temporal.ZonedDateTime} */ (day).with({
            hour,
            minute,
            second,
        });
    }

    /**
     * @param {number} valueIndex
     * @returns {string}
     */
    formatBound(valueIndex) {
        const value = this.values[valueIndex];
        if (!value) {
            return valueIndex === this.props.focusedDateIndex
                ? _t("Select a date")
                : _t("Not set");
        }
        return toLocaleString(value, {
            weekday: "short",
            month: "short",
            day: "numeric",
            year: value.year === this.today.year ? undefined : "numeric",
        });
    }

    /** @param {number} valueIndex */
    selectBound(valueIndex) {
        this.props.onBoundSelect?.(valueIndex);
    }

    /** @param {number} valueIndex */
    clearBound(valueIndex) {
        const value = [...this.values];
        value[valueIndex] = false;
        this.props.onSelect?.(value, "range", valueIndex);
    }

    /** @param {RangePreset} preset */
    applyPreset(preset) {
        if (!preset.isValid) {
            return;
        }
        const [start] = /** @type {DateTime[]} */ (preset.value);
        this.state.focusDate = this.clamp(startOf(start, "month"));
        this.state.precision = this.allowedPrecisionLevels[0];
        this.props.onSelect?.(preset.value, "range", 1);
    }

    /**
     * Places a picked day into the range without undoing the other bound:
     * a new start after the end carries the end along by the range's length,
     * and a new end before the start's day becomes the start instead.
     *
     * @param {DateTime} picked
     * @param {number} valueIndex
     * @returns {{ value: NullableDateValue[], focusedDateIndex: number }}
     */
    placeInRange(picked, valueIndex) {
        let [start, end] = this.values;
        if (valueIndex === 0) {
            const length =
                start && end && compareDates(end, start) >= 0
                    ? /** @type {Temporal.ZonedDateTime} */ (end).since(
                          /** @type {Temporal.ZonedDateTime} */ (start),
                      )
                    : null;
            if (end && compareDates(end, picked) < 0) {
                end = length ? picked.add(length) : false;
            }
            return { value: [picked, end], focusedDateIndex: 1 };
        }
        if (start && compareDates(startOf(picked, "day"), startOf(start, "day")) < 0) {
            if (isDateValue(start)) {
                start = picked;
            } else {
                const { hour, minute, second } = start;
                start = /** @type {Temporal.ZonedDateTime} */ (picked).with({
                    hour,
                    minute,
                    second,
                });
            }
            return {
                value: [start, end && compareDates(end, start) >= 0 ? end : false],
                focusedDateIndex: 1,
            };
        }
        return {
            value: [start, picked],
            focusedDateIndex: !start || compareDates(picked, start) >= 0 ? 0 : 1,
        };
    }

    /**
     * @param {Item[]} grid
     * @returns {Item[]}
     */
    decorateGrid(grid) {
        const { dayCellClass, isDateValid } = this.props;
        if (!isDateValid && !dayCellClass) {
            return grid;
        }
        return grid.map((item) => {
            const weeks = /** @type {MonthItem} */ (item).weeks;
            if (!weeks) {
                return item;
            }
            return {
                .../** @type {MonthItem} */ (item),
                weeks: weeks.map((week) => ({
                    ...week,
                    days: week.days.map((day) => {
                        const date = day.range[0];
                        return {
                            ...day,
                            isValid: day.isValid && (isDateValid?.(date) ?? true),
                            extraClass: dayCellClass?.(date) || "",
                        };
                    }),
                })),
            };
        });
    }

    /**
     * @param {NullableDateValue[]} values
     * @param {number} focusedDateIndex
     * @param {DateTime} today
     */
    adjustFocus(values, focusedDateIndex, today) {
        if (!this.shouldAdjustFocusDate && this.state.focusDate) {
            return;
        }

        const dateToFocus = this.getDateToFocus(values, focusedDateIndex) || today;

        this.shouldAdjustFocusDate = false;
        this.state.focusDate = this.clamp(startOf(dateToFocus, "month"));
    }

    /**
     * @param {NullableDateValue[]} values
     * @param {number} focusedDateIndex
     * @returns {NullableDateValue}
     */
    getDateToFocus(values, focusedDateIndex) {
        if (!this.shouldAdjustFocusDate && this.state.focusDate) {
            return null;
        }
        return values[focusedDateIndex] || values[focusedDateIndex === 1 ? 0 : 1];
    }

    /** @param {DateTime} value */
    clamp(value) {
        return clampDate(value, this.minDate, this.maxDate);
    }

    /**
     * A value clamped onto a limit takes the limit's seconds and milliseconds;
     * it moves inward to the first time the time picker could have offered.
     *
     * @param {DateTime} value
     * @returns {DateTime}
     */
    clampToStep(value) {
        const clamped = this.clamp(value);
        if (areDatesEqual(clamped, value) || isDateValue(clamped)) {
            return clamped;
        }
        const { rounding } = this.props;
        const up = areDatesEqual(clamped, this.minDate);
        const steps = rounding > 1 ? [rounding, 1, 0] : rounding === 1 ? [1, 0] : [0];
        for (const step of steps) {
            const aligned = alignToStep(clamped, step, up);
            if (isInRange(aligned, [this.minDate, this.maxDate])) {
                return aligned;
            }
        }
        return clamped;
    }

    /**
     * @param {PrecisionLevel} minPrecision
     * @param {PrecisionLevel} maxPrecision
     */
    filterPrecisionLevels(minPrecision, maxPrecision) {
        const levels = [...PRECISION_LEVELS.keys()];
        return levels.slice(
            levels.indexOf(minPrecision),
            levels.indexOf(maxPrecision) + 1,
        );
    }

    /** @param {DateItem} item */
    getActiveRangeInfo({ range }) {
        const result = {
            isSelected: isInRange(this.selectedRange, range),
            isSelectStart: false,
            isSelectEnd: false,
        };

        if (this.props.range) {
            if (result.isSelected) {
                const [selectStart, selectEnd] = this.selectedRange.toSorted((a, b) =>
                    a && b
                        ? compareDates(a, b)
                        : Number(Boolean(a)) - Number(Boolean(b)),
                );
                result.isSelectStart = !selectStart || isInRange(selectStart, range);
                result.isSelectEnd = !selectEnd || isInRange(selectEnd, range);
            }
        } else {
            result.isSelectStart = result.isSelectEnd = result.isSelected;
        }

        return result;
    }

    /** @param {DateTimePickerProps} props */
    getTimeValues(props) {
        if (this.isDate) {
            return [];
        }
        const values = /** @type {NullableDateTime[]} */ (this.values);
        const timeValues = values.map((val, index) => {
            const isImplicitEnd = index === 1 && !values[1];
            const reference = val || (isImplicitEnd && values[0]) || now(this.zone);
            return new Time({
                hour: isImplicitEnd ? Math.min(reference.hour + 1, 23) : reference.hour,
                minute: val ? val.minute : 0,
                second: val ? val.second : 0,
            });
        });

        if (props.range) {
            return timeValues;
        } else {
            const values = [];
            values[props.focusedDateIndex] = timeValues[props.focusedDateIndex];
            return values;
        }
    }

    /** @param {DateItem | null} item */
    onDateHover(item) {
        if (item && this.isHidden(item)) {
            item = null;
        }
        if (this.props.range) {
            this.state.hoveredDate = item ? item.range[0] : null;
        }
    }

    /**
     * Beside another month, a day outside its own month is shown by its
     * neighbour: it is left blank rather than shown twice
     *
     * @param {DateItem} item
     */
    isHidden(item) {
        return item.isOutOfRange && this.monthCount > 1;
    }

    /** @param {PointerEvent} ev */
    next(ev) {
        ev.preventDefault();
        const { step } = this.activePrecisionLevel;
        this.state.focusDate = this.clamp(this.state.focusDate.add(step));
        if (this.state.cursorDate) {
            this.state.cursorDate = this.clampDay(this.state.cursorDate.add(step));
        }
    }

    /** @param {PointerEvent} ev */
    previous(ev) {
        ev.preventDefault();
        const { step } = this.activePrecisionLevel;
        this.state.focusDate = this.clamp(this.state.focusDate.subtract(step));
        if (this.state.cursorDate) {
            this.state.cursorDate = this.clampDay(this.state.cursorDate.subtract(step));
        }
    }

    /**
     * Keys typed in the owner's input: Up or Down hands the arrows to the
     * grid, where the arrows, Home/End and Page Up/Down move the cursor and
     * Enter or Space picks it. Typing gives them back to the text.
     *
     * @param {KeyboardEvent} ev
     * @returns {boolean} whether the key was used
     */
    onKeydown(ev) {
        const { key, altKey, ctrlKey, metaKey, shiftKey } = ev;
        if (altKey || ctrlKey || metaKey) {
            return false;
        }
        const cursor = this.state.cursorDate;
        if (!cursor) {
            if (key !== "ArrowDown" && key !== "ArrowUp") {
                return false;
            }
            this.moveCursor(this.getInitialCursor());
            return true;
        }
        if (key === "Enter" || key === " ") {
            const item = this.getDateItems().find((item) => this.isCursor(item));
            if (item) {
                this.zoomOrSelect(item);
            }
            return true;
        }
        const target = this.getCursorTarget(cursor, key, shiftKey);
        if (target) {
            this.moveCursor(target);
            return true;
        }
        if (key.length === 1 || key === "Backspace" || key === "Delete") {
            this.state.cursorDate = null;
            this.state.hoveredDate = null;
        }
        return false;
    }

    /** @returns {DateTime} */
    getInitialCursor() {
        const { focusedDateIndex } = this.props;
        const value =
            this.values[focusedDateIndex] || this.values[focusedDateIndex ? 0 : 1];
        return this.clampDay(value || this.today);
    }

    /**
     * @param {DateTime} cursor
     * @param {string} key
     * @param {boolean} shiftKey
     * @returns {DateTime | null}
     */
    getCursorTarget(cursor, key, shiftKey) {
        const { keySteps } = this.activePrecisionLevel;
        const page = shiftKey ? keySteps.bigPage : keySteps.page;
        const isDays = this.state.precision === "days";
        switch (key) {
            case "ArrowLeft":
                return cursor.subtract(keySteps.across);
            case "ArrowRight":
                return cursor.add(keySteps.across);
            case "ArrowUp":
                return cursor.subtract(keySteps.down);
            case "ArrowDown":
                return cursor.add(keySteps.down);
            case "PageUp":
                return cursor.subtract(page);
            case "PageDown":
                return cursor.add(page);
            case "Home":
                return isDays ? getStartOfLocalWeek(cursor) : null;
            case "End":
                return isDays ? getStartOfLocalWeek(cursor).add({ days: 6 }) : null;
        }
        return null;
    }

    /**
     * Puts the cursor on a day and turns the grid to it; while a range is
     * picked, the cursor previews the range as the pointer does
     *
     * @param {DateTime} date
     */
    moveCursor(date) {
        const cursor = this.clampDay(date);
        this.state.cursorDate = cursor;
        if (this.props.range && this.state.precision === "days") {
            this.state.hoveredDate = cursor;
        }
        const shown = this.getDateItems().some(
            (item) => !item.isOutOfRange && isInRange(cursor, item.range),
        );
        if (shown) {
            return;
        }
        if (this.state.precision !== "days") {
            this.state.focusDate = this.clamp(cursor);
            return;
        }
        const month = startOf(cursor, "month");
        this.state.focusDate = this.clamp(
            compareDates(cursor, this.state.focusDate) < 0
                ? month
                : month.subtract({ months: this.monthCount - 1 }),
        );
    }

    /** @param {DateTime} date */
    clampDay(date) {
        return startOf(
            clampDate(date, startOf(this.minDate, "day"), this.maxDate),
            "day",
        );
    }

    /** @returns {DateItem[]} the grid's cells, the days of every month shown */
    getDateItems() {
        return this.items.flatMap((item) =>
            "weeks" in item
                ? item.weeks.flatMap((week) => week.days)
                : [/** @type {DateItem} */ (item)],
        );
    }

    /** @param {DateItem} item */
    isCursor(item) {
        const cursor = this.state.cursorDate;
        return Boolean(cursor && !this.isHidden(item) && isInRange(cursor, item.range));
    }

    /**
     * @param {number} valueIndex
     * @param {Time} newTime
     */
    onTimeChange(valueIndex, newTime) {
        this.state.timeValues[valueIndex] = newTime;
        const value = this.values[valueIndex] || this.today;
        this.selectIfValid(value, valueIndex, "time");
    }

    /**
     * @param {DateTime} value
     * @param {number} valueIndex
     * @param {"date" | "time"} unit
     */
    selectIfValid(value, valueIndex, unit) {
        if (!this.props.onSelect) {
            return false;
        }

        /** @type {NullableDateValue[]} */
        const result = [...this.values];
        result[valueIndex] = value;

        if (this.props.type === "datetime") {
            const { hour, minute, second } = this.state.timeValues[valueIndex];
            result[valueIndex] = /** @type {Temporal.ZonedDateTime} */ (
                result[valueIndex]
            ).with({
                hour,
                minute,
                second,
            });
        }
        if (unit === "date") {
            const clicked = /** @type {DateTime} */ (result[valueIndex]);
            const clamped = this.clampToStep(clicked);
            result[valueIndex] = clamped;
            if (!areDatesEqual(clamped, clicked)) {
                log.logic("selectIfValid clamped", () => ({
                    clicked: String(clicked),
                    value: String(clamped),
                    rounding: this.props.rounding,
                    minDate: String(this.minDate),
                    maxDate: String(this.maxDate),
                    valueIndex,
                }));
            }
        }
        if (!isInRange(result[valueIndex], [this.minDate, this.maxDate])) {
            log.logic("selectIfValid rejected", () => ({
                value: String(result[valueIndex]),
                valueIndex,
                unit,
            }));
            return false;
        }
        log.logic("select", () => ({
            value: String(result[valueIndex]),
            valueIndex,
            unit,
        }));
        if (this.props.range && result.length === 2 && unit === "date") {
            const placed = this.placeInRange(result[valueIndex], valueIndex);
            this.props.onSelect(placed.value, unit, placed.focusedDateIndex);
            return true;
        }
        this.props.onSelect(result.length === 2 ? result : result[0], unit);
        return true;
    }

    /** @param {DateTime} date */
    zoomIn(date) {
        const index = this.allowedPrecisionLevels.indexOf(this.state.precision) - 1;
        if (index in this.allowedPrecisionLevels) {
            this.state.focusDate = this.clamp(date);
            this.state.precision = this.allowedPrecisionLevels[index];
            return true;
        }
        return false;
    }

    zoomOut() {
        const index = this.allowedPrecisionLevels.indexOf(this.state.precision) + 1;
        if (index in this.allowedPrecisionLevels) {
            this.state.precision = this.allowedPrecisionLevels[index];
            return true;
        }
        return false;
    }

    /** @param {DateItem} dateItem */
    zoomOrSelect(dateItem) {
        if (!dateItem.isValid || this.isHidden(dateItem)) {
            return;
        }
        if (
            this.state.cursorDate &&
            !isInRange(this.state.cursorDate, dateItem.range)
        ) {
            this.state.cursorDate = this.clampDay(dateItem.range[0]);
        }
        if (this.zoomIn(dateItem.range[0])) {
            return;
        }
        const [value] = dateItem.range;
        const valueIndex = this.props.focusedDateIndex;
        this.selectIfValid(value, valueIndex, "date");
    }
}
