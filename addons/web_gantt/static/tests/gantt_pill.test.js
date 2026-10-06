import { describe, expect, test } from "@odoo/hoot";
import { parseISO, toISO } from "@web/core/l10n/dates";
import {
    durationLabel,
    pillBounds,
    pillDecorationClasses,
    pillLabel,
} from "@web_gantt/gantt_pill";

describe.current.tags("headless");

const dt = (iso) => parseISO(iso);

test("pillBounds clips to the range and locks the clipped edge", () => {
    const params = {
        dateStartField: "start",
        dateStopField: "stop",
        stopIsDate: false,
        globalStart: dt("2019-01-10T00:00"),
        globalStop: dt("2019-01-20T00:00"),
        canEdit: true,
        disableDrag: false,
    };
    const inside = pillBounds(
        { start: dt("2019-01-12T08:00"), stop: dt("2019-01-13T08:00") },
        params,
    );
    expect(toISO(inside.start)).toBe(toISO(dt("2019-01-12T08:00")));
    expect(inside).toMatchObject({
        disableDrag: false,
        disableStartResize: false,
        disableStopResize: false,
    });
    const before = pillBounds(
        { start: dt("2019-01-05T08:00"), stop: dt("2019-01-13T08:00") },
        params,
    );
    expect(toISO(before.start)).toBe(toISO(params.globalStart));
    expect(before).toMatchObject({
        disableDrag: true,
        disableStartResize: true,
        disableStopResize: false,
    });
    const readonly = pillBounds(
        { start: dt("2019-01-12T08:00"), stop: dt("2019-01-13T08:00") },
        { ...params, canEdit: false },
    );
    expect(readonly).toMatchObject({
        disableDrag: true,
        disableStartResize: true,
        disableStopResize: true,
    });
    // A date-typed stop covers its whole day.
    const dated = pillBounds(
        { start: dt("2019-01-12"), stop: dt("2019-01-19") },
        { ...params, stopIsDate: true },
    );
    expect(toISO(dated.stop)).toBe(toISO(dt("2019-01-20")));
    expect(dated.disableStopResize).toBe(false);
});

test("pillDecorationClasses evaluates each expression against serialised values", () => {
    const fields = {
        start: { type: "datetime" },
        day: { type: "date" },
        qty: { type: "integer" },
    };
    const record = { start: dt("2019-01-12T08:00"), day: dt("2019-01-12"), qty: 3 };
    const classes = pillDecorationClasses(
        record,
        fields,
        {
            "decoration-info": "qty > 2",
            "decoration-danger": "qty > 5",
            "decoration-warning": "day == '2019-01-12'",
            "decoration-success": "start and uid == 7",
        },
        { uid: 7 },
    );
    expect(classes).toEqual([
        "decoration-info",
        "decoration-warning",
        "decoration-success",
    ]);
});

test("durationLabel spells hours and minutes the way the pill shows them", () => {
    expect(durationLabel(4)).toBe(" (4h)");
    expect(durationLabel(4.5)).toBe(" (4h30)");
    expect(durationLabel(0.25)).toBe(" (0h15)");
});

test("pillLabel: dates on the year scale, times and duration on week and month", () => {
    const base = {
        displayName: "Task",
        startDate: dt("2019-01-12T08:00"),
        stopDate: dt("2019-01-12T12:00"),
        rangeStart: dt("2019-01-01"),
        rangeStop: dt("2019-01-31"),
        duration: 4,
        durationStr: " (4h)",
    };
    expect(pillLabel({ ...base, scaleId: "year" })).toBe("1/12 Task");
    expect(
        pillLabel({ ...base, scaleId: "year", stopDate: dt("2019-01-16T12:00") }),
    ).toBe("1/12 - 1/16 Task");
    expect(pillLabel({ ...base, scaleId: "week" })).toBe(
        "8:00 AM - 12:00 PM (4h) Task",
    );
    // On the month scale a timed pill drops its own name.
    expect(pillLabel({ ...base, scaleId: "month" })).toBe("8:00 AM - 12:00 PM (4h)");
    expect(pillLabel({ ...base, scaleId: "month", duration: 0, durationStr: "" })).toBe(
        "Task",
    );
    expect(pillLabel({ ...base, scaleId: "day" })).toBe("Task");
    // A span across days shows dates only when it leaves the visible range.
    const span = { ...base, scaleId: "week", stopDate: dt("2019-01-16T12:00") };
    expect(pillLabel(span)).toBe("Task");
    expect(pillLabel({ ...span, rangeStop: dt("2019-01-14") })).toBe(
        "1/12 - 1/16 Task",
    );
});
