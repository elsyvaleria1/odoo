// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { proxy, toRaw } from "@odoo/owl";

describe.current.tags("headless");

test(`Temporal objects can't be made reactive`, async () => {
    const obj = proxy({
        ZonedDateTime: Temporal.Now.zonedDateTimeISO("UTC"),
        Instant: Temporal.Now.instant(),
        PlainDate: Temporal.PlainDate.from("2024-02-29"),
        PlainDateTime: Temporal.PlainDateTime.from("2024-02-29T13:45:07"),
        PlainTime: Temporal.PlainTime.from("13:45:07"),
        PlainYearMonth: Temporal.PlainYearMonth.from("2024-02"),
        PlainMonthDay: Temporal.PlainMonthDay.from("--02-29"),
        Duration: Temporal.Duration.from({ seconds: 10 }),
    });
    expect(obj.ZonedDateTime).toBe(toRaw(obj.ZonedDateTime));
    expect(obj.Instant).toBe(toRaw(obj.Instant));
    expect(obj.PlainDate).toBe(toRaw(obj.PlainDate));
    expect(obj.PlainDateTime).toBe(toRaw(obj.PlainDateTime));
    expect(obj.PlainTime).toBe(toRaw(obj.PlainTime));
    expect(obj.PlainYearMonth).toBe(toRaw(obj.PlainYearMonth));
    expect(obj.PlainMonthDay).toBe(toRaw(obj.PlainMonthDay));
    expect(obj.Duration).toBe(toRaw(obj.Duration));
});
