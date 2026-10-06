/** @odoo-module */

import {
    advanceTime,
    beforeEach,
    describe,
    expect,
    freezeTime,
    mockDate,
    mockTimeZone,
    test,
} from "@odoo/hoot";

import { parseUrl } from "../local_helpers.js";

describe(parseUrl(import.meta.url), () => {
    beforeEach(freezeTime);

    test("Temporal.Now.instant follows the mocked date", () => {
        mockDate("2024-02-29 13:45:00");

        expect(Temporal.Now.instant().epochMilliseconds).toBe(Date.now());
        expect(Temporal.Now.instant().toString()).toBe("2024-02-29T13:45:00Z");
    });

    test("Temporal.Now follows advanced time", async () => {
        mockDate("2024-02-29 13:45:00");

        await advanceTime(90_000);

        expect(Temporal.Now.instant().toString()).toBe("2024-02-29T13:46:30Z");
    });

    test("Temporal.Now defaults to the mocked time zone", () => {
        mockDate("2024-07-01 10:00:00", "America/Mexico_City");

        expect(Temporal.Now.timeZoneId()).toBe("America/Mexico_City");
        expect(Temporal.Now.plainDateTimeISO().toString()).toBe("2024-07-01T04:00:00");
        expect(Temporal.Now.plainDateISO().toString()).toBe("2024-07-01");
        expect(Temporal.Now.plainTimeISO().toString()).toBe("04:00:00");
        expect(Temporal.Now.zonedDateTimeISO().offset).toBe("-06:00");
    });

    test("a numeric mocked time zone is an offset zone", () => {
        mockDate("2024-07-01 10:00:00");
        mockTimeZone(5.5);

        expect(Temporal.Now.timeZoneId()).toBe("+05:30");
        expect(Temporal.Now.plainTimeISO().toString()).toBe("15:30:00");

        mockTimeZone(-3);

        expect(Temporal.Now.timeZoneId()).toBe("-03:00");
        expect(Temporal.Now.plainTimeISO().toString()).toBe("07:00:00");
    });

    test("an explicit time zone overrides the mocked one", () => {
        mockDate("2024-07-01 10:00:00", "America/Mexico_City");

        expect(Temporal.Now.plainDateTimeISO("UTC").toString()).toBe(
            "2024-07-01T10:00:00",
        );
        expect(Temporal.Now.zonedDateTimeISO("Asia/Tokyo").hour).toBe(19);
    });

    test("Temporal.Now defaults to the fixed offset the mocked Date uses", () => {
        mockDate("2024-07-15 12:00:00");

        expect(Temporal.Now.timeZoneId()).toBe("+01:00");
        expect(Temporal.Now.plainTimeISO().toString()).toBe("13:00:00");
        expect(Temporal.Now.zonedDateTimeISO().offset).toBe("+01:00");
        expect(new Date().getTimezoneOffset()).toBe(-60);
    });

    test("an offset of a day or more is refused", () => {
        expect(() => mockTimeZone(24)).toThrow(/within ±24 hours/);
        expect(() => mockTimeZone(-40)).toThrow(/within ±24 hours/);
    });

    test("the rest of Temporal is the real one", () => {
        expect(Temporal.PlainDate.from("2024-02-29").add({ years: 1 }).toString()).toBe(
            "2025-02-28",
        );
        expect(
            Temporal.Duration.from({ hours: 25 }).round({
                largestUnit: "day",
                relativeTo: "2024-01-01",
            }).days,
        ).toBe(1);
    });
});
