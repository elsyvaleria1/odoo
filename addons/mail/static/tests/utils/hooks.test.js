// @ts-check
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { useHover, useLongPress, useMessageScrolling } from "@mail/utils/common/hooks";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, hover, leave, queryOne, runAllTimers } from "@odoo/hoot-dom";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { elementRef } from "@web/core/utils/element_ref";

describe.current.tags("desktop");
defineMailModels();

function touch(selector, type, { clientX = 0, clientY = 0, fingers = 1 } = {}) {
    const ev = Object.assign(new Event(type, { bubbles: true }), {
        touches: Array.from({ length: fingers }, () => ({ clientX, clientY })),
    });
    queryOne(selector).dispatchEvent(ev);
}

class LongPressTarget extends Component {
    static props = {};
    static template = xml`<div class="test-longpress" t-ref="this.rootRef">press me</div>`;
    props = useProps(this.constructor.props);

    setup() {
        this.rootRef = elementRef();
        useLongPress(this.rootRef, { action: () => expect.step("long-press") });
    }
}

class LongPressParent extends Component {
    static components = { LongPressTarget };
    static props = {};
    static template = xml`<LongPressTarget t-if="this.state.mounted"/>`;
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ mounted: true });
    }
}

test("useHover cancels its pending timers on unmount", async () => {
    class HoverTarget extends Component {
        static props = {};
        static template = xml`<div class="test-hover" t-ref="this.rootRef">hover me</div>`;
        props = useProps(this.constructor.props);

        setup() {
            this.rootRef = elementRef();
            this.hover = useHover(this.rootRef, {
                onAway: () => expect.step("away"),
                onHovering: [5000, () => expect.step("hovering")],
            });
        }
    }
    class Parent extends Component {
        static components = { HoverTarget };
        static props = {};
        static template = xml`<HoverTarget t-if="this.state.mounted"/>`;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({ mounted: true });
        }
    }
    const parent = await mountWithCleanup(Parent);
    await hover(".test-hover");
    await leave();
    parent.state.mounted = false;
    await animationFrame();
    await runAllTimers();
    expect.verifySteps([]);
});

test("useLongPress fires its action once the delay elapses", async () => {
    await mountWithCleanup(LongPressParent);
    touch(".test-longpress", "touchstart");
    await runAllTimers();
    expect.verifySteps(["long-press"]);
});

test("useLongPress cancels its pending timer on unmount", async () => {
    const parent = await mountWithCleanup(LongPressParent);
    touch(".test-longpress", "touchstart");
    parent.state.mounted = false;
    await animationFrame();
    await runAllTimers();
    expect.verifySteps([]);
});

test("useLongPress leaves no orphan timer when a second finger lands", async () => {
    await mountWithCleanup(LongPressParent);
    touch(".test-longpress", "touchstart");
    touch(".test-longpress", "touchstart", { fingers: 2 });
    touch(".test-longpress", "touchend");
    await runAllTimers();
    expect.verifySteps([]);
});

test("useLongPress fires once when touchstart repeats before the delay", async () => {
    await mountWithCleanup(LongPressParent);
    touch(".test-longpress", "touchstart");
    touch(".test-longpress", "touchstart");
    await runAllTimers();
    expect.verifySteps(["long-press"]);
});

class ScrollingHost extends Component {
    static props = {};
    static template = xml`
        <div class="test-other-scroller" style="height: 50px; overflow-y: auto;">
            <div style="height: 500px;"/>
        </div>
        <div class="test-scroller" style="height: 100px; overflow-y: auto;">
            <div class="test-top" style="height: 20px;">top</div>
            <div style="height: 800px;"/>
            <div class="test-bottom" style="height: 20px;">bottom</div>
        </div>`;
    props = useProps(this.constructor.props);

    setup() {
        this.scrolling = useMessageScrolling();
    }
}

test("scrollTo settles at once when the element is already where it would scroll", async () => {
    const host = await mountWithCleanup(ScrollingHost);
    let settled = false;
    host.scrolling.scrollTo(queryOne(".test-top")).then(() => (settled = true));
    await animationFrame();
    expect(settled).toBe(true);
});

test("scrollTo waits for its own scroller's scrollend, not another's", async () => {
    const host = await mountWithCleanup(ScrollingHost);
    let settled = false;
    host.scrolling.scrollTo(queryOne(".test-bottom")).then(() => (settled = true));
    queryOne(".test-other-scroller").dispatchEvent(new Event("scrollend"));
    await Promise.resolve();
    await Promise.resolve();
    expect(settled).toBe(false);
    queryOne(".test-scroller").dispatchEvent(new Event("scrollend"));
    await Promise.resolve();
    await Promise.resolve();
    expect(settled).toBe(true);
});
