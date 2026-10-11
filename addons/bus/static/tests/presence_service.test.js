import { defineBusModels } from "@bus/../tests/bus_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
    getService,
    makeMockEnv,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

defineBusModels();
describe.current.tags("desktop");

test("J18: blur triggers window_focus(false)", async () => {
    const env = await makeMockEnv();
    getService("presence");
    const focusEvents = [];
    env.bus.addEventListener("window_focus", ({ detail }) => focusEvents.push(detail));
    browser.dispatchEvent(new Event("blur"));
    expect(focusEvents).toInclude(false);
    expect(focusEvents).not.toInclude(true);
});

test("J18: a storage event with null newValue keeps inactivity sane", async () => {
    await makeMockEnv();
    const presence = getService("presence");
    browser.dispatchEvent(
        new StorageEvent("storage", {
            key: "presence.lastPresence",
            newValue: null,
        }),
    );
    const inactivity = presence.getInactivityPeriod();
    expect(inactivity).toBeGreaterThanOrEqual(0);
    expect(inactivity).toBeLessThan(60_000);
});

test("J18: a bfcache pageshow restores the real focus state", async () => {
    const env = await makeMockEnv();
    getService("presence");
    browser.dispatchEvent(new Event("pagehide"));
    const focusEvents = [];
    env.bus.addEventListener("window_focus", ({ detail }) => focusEvents.push(detail));
    patchWithCleanup(document, { hasFocus: () => true });
    browser.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    expect(focusEvents).toInclude(true);
    expect(focusEvents).not.toInclude(false);
});
