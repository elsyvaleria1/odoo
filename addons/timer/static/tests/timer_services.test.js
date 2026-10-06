import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { TimerReactive } from "@timer/models/timer_reactive";
import { makeMockEnv } from "@web/../tests/web_test_helpers";
import { now } from "@web/core/l10n/dates";

defineMailModels();

test("timer_reactive handle displaying start time", async () => {
    const env = await makeMockEnv();
    const timerReactive = new TimerReactive(env);
    timerReactive.formatTime();
    expect(timerReactive.time).toBe("00:00:00");

    const currentTime = now();
    const timerStart = currentTime.subtract({ seconds: 1 });
    timerReactive.computeOffset(currentTime);
    timerReactive.setTimer(0, timerStart, currentTime);
    timerReactive.formatTime();
    expect(timerReactive.time).toBe("00:00:01");
});

test("timer_reactive handle displaying durations longer than 24h", async () => {
    const env = await makeMockEnv();
    const timerReactive = new TimerReactive(env);
    const currentTime = now();
    const timerStart = currentTime.add({ days: 2 });
    timerReactive.computeOffset(currentTime);
    timerReactive.setTimer(0, timerStart, currentTime);
    timerReactive.formatTime();
    expect(timerReactive.time).toBe("48:00:00");
});
