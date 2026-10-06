// @ts-check

import { after, describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { isolateLogging } from "@web/../tests/core/debug/logging_helpers";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import {
    disableLogging,
    enableLogging,
    getStats,
    makeLogger,
} from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";

describe.current.tags("headless");

/** @param {() => unknown} body */
async function captureConsoleDebug(body) {
    /** @type {any[][]} */
    const captured = [];
    const original = console.debug;
    console.debug = (...args) => captured.push(args);
    try {
        await body();
    } finally {
        console.debug = original;
    }
    return captured;
}

/** @param {any[][]} captured */
function labels(captured) {
    return captured.map((args) => args[0].replace(/%c/g, ""));
}

function cleanLogging() {
    after(isolateLogging());
}

function makeProbe() {
    const log = makeLogger("test.hooks");
    class Probe extends Component {
        static template = xml`<span><t t-out="this.state.tick"/></span>`;
        static props = {};
        props = useProps(this.constructor.props);
        setup() {
            useLifecycleLog(log);
            this.state = proxy({ tick: 0 });
        }
    }
    return Probe;
}

test("registers no willStart and no willUpdateProps: a mount awaits nothing extra", async () => {
    expect.assertions(2);
    cleanLogging();
    /** @type {number[]} */
    let added = [];
    const log = makeLogger("test.hooks");
    class Probe extends Component {
        static template = xml`<span/>`;
        static props = {};
        props = useProps(this.constructor.props);
        setup() {
            const node = /** @type {any} */ (this).__owl__;
            const before = [node.willStart.length, node.willUpdateProps.length];
            useLifecycleLog(log);
            added = [
                node.willStart.length - before[0],
                node.willUpdateProps.length - before[1],
            ];
        }
    }
    await mountWithCleanup(Probe);
    expect(added[0]).toBe(0);
    expect(added[1]).toBe(0);
});

test("logs nothing and records nothing when the namespace is off", async () => {
    expect.assertions(2);
    cleanLogging();
    disableLogging({ persist: false });
    const Probe = makeProbe();
    const captured = await captureConsoleDebug(async () => {
        const probe = await mountWithCleanup(Probe);
        probe.state.tick = 1;
        await animationFrame();
    });
    expect(captured).toHaveLength(0);
    expect(getStats()).toHaveLength(0);
});

test("logs setup, mounted and a patch pair per update", async () => {
    expect.assertions(3);
    cleanLogging();
    enableLogging("test.hooks", { persist: false });
    const Probe = makeProbe();
    const captured = await captureConsoleDebug(async () => {
        const probe = await mountWithCleanup(Probe);
        probe.state.tick = 1;
        await animationFrame();
    });
    const seen = labels(captured);
    expect(seen[0]).toBe("[test.hooks] lifecycle Probe setup");
    expect(seen).toInclude("[test.hooks] lifecycle Probe mounted");
    expect(seen.filter((label) => /willPatch#1|patched#1/.test(label))).toHaveLength(2);
});

test("patch spans are measured, so the stats table can rank them", async () => {
    expect.assertions(3);
    cleanLogging();
    enableLogging("test.hooks:perf", { persist: false });
    const Probe = makeProbe();
    const captured = await captureConsoleDebug(async () => {
        const probe = await mountWithCleanup(Probe);
        probe.state.tick = 1;
        await animationFrame();
    });
    const rows = Object.fromEntries(getStats().map((row) => [row.label, row]));
    expect(rows["Probe patch"].count).toBe(1);
    expect(rows["Probe render"]).toBe(undefined);
    expect(
        labels(captured).map((label) =>
            label.replace(/^\[test\.hooks\] perf Probe (\w+) \d+\.\d\dms$/, "$1"),
        ),
    ).toEqual(["patch"]);
});
