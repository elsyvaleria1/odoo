// @ts-check

import { describe, expect, getFixture, test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-mock";
import { getService, makeMockEnv } from "@web/../tests/web_test_helpers";
import { makeLogger } from "@web/core/debug/debug_logger";

describe.current.tags("headless");
const log = makeLogger("web.core.audit");

test("double cleanup() is a no-op (does not crash)", async () => {
    await makeMockEnv();
    const sortable = await getService("sortable");

    const fixture = getFixture();
    const root = document.createElement("div");
    const item = document.createElement("div");
    item.className = "item";
    root.appendChild(item);
    fixture.appendChild(root);

    const handle = sortable.create({
        ref: { el: root },
        elements: ".item",
    });
    const { cleanup } = handle.enable();

    cleanup();
    expect(() => cleanup()).not.toThrow();
});

test("enable() is idempotent — a second call does not re-arm listeners", async () => {
    await makeMockEnv();
    const sortable = await getService("sortable");

    const fixture = getFixture();
    const root = document.createElement("div");
    const item = document.createElement("div");
    item.className = "item";
    root.appendChild(item);
    fixture.appendChild(root);

    const handle = sortable.create({ ref: { el: root }, elements: ".item" });
    const first = handle.enable();
    /** @type {any} */
    let second;
    expect(() => {
        second = handle.enable();
    }).not.toThrow();
    expect(typeof first.cleanup).toBe("function");
    expect(typeof second.cleanup).toBe("function");
    first.cleanup();
});

test("cleanup() disarms the element: a later pointerdown starts nothing", async () => {
    const { pointerDown, pointerUp } = await import("@odoo/hoot-dom");
    await makeMockEnv();
    const sortable = await getService("sortable");

    const fixture = getFixture();
    const root = document.createElement("div");
    const item = document.createElement("div");
    item.className = "item";
    root.appendChild(item);
    fixture.appendChild(root);

    const handle = sortable.create({
        ref: { el: root },
        elements: ".item",
        delay: 10,
        onWillStartDrag: () => {
            log.logic("sortable service starts while armed");
            expect.step("will-start");
        },
    });
    const { cleanup } = handle.enable();
    await pointerDown(item);
    await advanceTime(10);
    await pointerUp(item);
    expect.verifySteps(["will-start"]);

    cleanup();
    await pointerDown(item);
    await advanceTime(10);
    await pointerUp(item);
    expect.verifySteps([]);
    log.logic("sortable service stays disarmed after initiation delay");
});

/** @param {HTMLElement} root */
function appendItem(root) {
    const item = document.createElement("div");
    item.className = "item";
    root.appendChild(item);
    return item;
}

test("enable() after cleanup() re-arms the element", async () => {
    const { pointerDown, pointerUp } = await import("@odoo/hoot-dom");
    await makeMockEnv();
    const sortable = await getService("sortable");
    const root = document.createElement("div");
    const item = appendItem(root);
    getFixture().appendChild(root);

    const handle = sortable.create({
        ref: { el: root },
        elements: ".item",
        delay: 10,
        onWillStartDrag: () => expect.step("will-start"),
    });
    const drag = async () => {
        await pointerDown(item);
        await advanceTime(10);
        await pointerUp(item);
    };

    handle.enable().cleanup();
    await drag();
    expect.verifySteps([]);

    const { cleanup } = handle.enable();
    await drag();
    expect.verifySteps(["will-start"]);
    log.logic("sortable service re-armed after cleanup");

    cleanup();
    await drag();
    expect.verifySteps([]);
});

test("a cleaned-up handle re-enabled over a newer sortable on the same element fails loudly", async () => {
    await makeMockEnv();
    const sortable = await getService("sortable");
    const root = document.createElement("div");
    appendItem(root);
    getFixture().appendChild(root);

    const first = sortable.create({ ref: { el: root }, elements: ".item" });
    first.enable().cleanup();
    const second = sortable.create({ ref: { el: root }, elements: ".item" });
    const { cleanup } = second.enable();

    expect(() => first.enable()).toThrow(/another sortable holds this element/);
    cleanup();
});

test("a stale handle's cleanup() leaves the newer sortable bound", async () => {
    await makeMockEnv();
    const sortable = await getService("sortable");
    const root = document.createElement("div");
    appendItem(root);
    getFixture().appendChild(root);

    const first = sortable.create({ ref: { el: root }, elements: ".item" });
    const { cleanup: firstCleanup } = first.enable();
    firstCleanup();
    const second = sortable.create({ ref: { el: root }, elements: ".item" });
    const { cleanup: secondCleanup } = second.enable();

    firstCleanup();
    const third = sortable.create({ ref: { el: root }, elements: ".item" });
    expect(third.enable().cleanup).toBe(secondCleanup);
    secondCleanup();
});
