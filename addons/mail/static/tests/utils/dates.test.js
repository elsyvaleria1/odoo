// @ts-check
import { computeDelay, getMsToTomorrow, isToday } from "@mail/utils/common/dates";
import { beforeEach, describe, expect, mockDate, test } from "@odoo/hoot";
import { freezeTime } from "@odoo/hoot-dom";
import { dateSettings, now, toDateTime, today, toISO } from "@web/core/l10n/dates";

const userZone = (hours) =>
    `${hours < 0 ? "-" : "+"}${String(Math.abs(hours)).padStart(2, "0")}:00`;

describe.current.tags("headless");

beforeEach(freezeTime);

function withUserZone(zone, fn) {
    const previous = dateSettings.timeZone;
    dateSettings.timeZone = zone;
    try {
        return fn();
    } finally {
        dateSettings.timeZone = previous;
    }
}

test("getMsToTomorrow lands on midnight in the user's timezone", () => {
    mockDate("2026-03-10T16:00:00", 0);
    withUserZone(userZone(9), () => {
        const ms = getMsToTomorrow();
        const landing = now().add({ milliseconds: ms });
        expect(toISO(landing)).toBe(toISO(now().add({ days: 1 }).startOfDay()), {
            message: "the timer must fire at the user's midnight, not the browser's",
        });
        expect(Math.round(ms / 3600000)).toBe(23);
    });
});

test("getMsToTomorrow lands where computeDelay changes its answer", () => {
    mockDate("2026-03-10T16:00:00", 0);
    withUserZone(userZone(9), () => {
        const landing = now().add({ milliseconds: getMsToTomorrow() });
        expect(landing.hour).toBe(0, { message: "the timer fires at a midnight" });
        expect(landing.epochMilliseconds).toBe(
            toDateTime(today().add({ days: 1 })).epochMilliseconds,
            {
                message: "...and specifically the user's next midnight",
            },
        );
        const deadline = today();
        expect(computeDelay(deadline)).toBe(0);
    });
});

test("the browser's midnight is genuinely a different instant here", () => {
    mockDate("2026-03-10T16:00:00", 0);
    const browserMidnight = new Date(2026, 2, 11, 0, 0, 0).getTime();
    withUserZone(userZone(9), () => {
        const userMidnight = toDateTime(today().add({ days: 1 })).epochMilliseconds;
        expect(userMidnight).not.toBe(browserMidnight);
    });
});

test("getMsToTomorrow is positive and under 24h in every zone", () => {
    mockDate("2026-03-10T16:00:00", 0);
    for (const zone of [userZone(0), userZone(9), userZone(-5), userZone(14)]) {
        withUserZone(zone, () => {
            const ms = getMsToTomorrow();
            expect(ms > 0 && ms <= 24 * 3600 * 1000).toBe(true, {
                message: `offset ${zone}: expected a positive sub-24h delay, got ${ms}`,
            });
        });
    }
});

test("isToday and computeDelay share the user's timezone", () => {
    mockDate("2026-03-10T16:00:00", 0);
    withUserZone(userZone(9), () => {
        const userToday = today();
        expect(isToday(now())).toBe(true);
        expect(isToday(userToday)).toBe(true);
        expect(computeDelay(userToday)).toBe(0);
        expect(isToday(now().subtract({ days: 1 }))).toBe(false);
        expect(isToday(userToday.subtract({ days: 1 }))).toBe(false);
    });
});
