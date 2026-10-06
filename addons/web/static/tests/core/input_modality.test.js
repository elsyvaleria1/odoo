// @ts-check

import { expect, test } from "@odoo/hoot";
import { queryRect } from "@odoo/hoot-dom";
import { animationFrame, mockMatchMedia, mockTouch } from "@odoo/hoot-mock";
import { Component, xml } from "@odoo/owl";
import {
    getService,
    makeMockEnv,
    mountWithCleanup,
    setInputModality,
} from "@web/../tests/web_test_helpers";
import { inputModality, useInputModality } from "@web/core/input_modality";

/** @param {string} pointerType */
function pointerDown(pointerType) {
    document.body.dispatchEvent(
        new PointerEvent("pointerdown", { pointerType, bubbles: true }),
    );
}

/** @param {string} key */
function keyDown(key) {
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

function published() {
    return document.documentElement.dataset.inputModality;
}

test("starts from the device's pointer: mouse", async () => {
    await makeMockEnv();
    expect(published()).toBe("mouse");
    expect(document.body).not.toHaveClass("o_touch_device");
    expect(getService("ui").inputModality).toBe("mouse");
});

test("starts from the device's pointer: touch", async () => {
    mockTouch(true);
    await makeMockEnv();
    expect(published()).toBe("touch");
    expect(document.body).toHaveClass("o_touch_device");
    expect(inputModality.isTouch).toBe(true);
});

test("follows the pointer the user actually uses", async () => {
    mockTouch(true);
    await makeMockEnv();
    pointerDown("mouse");
    expect(published()).toBe("mouse");
    expect(document.body).not.toHaveClass("o_touch_device");
    pointerDown("pen");
    expect(published()).toBe("pen");
    pointerDown("touch");
    expect(published()).toBe("touch");
    expect(document.body).toHaveClass("o_touch_device");
});

test("navigating with the keyboard is keyboard modality, typing is not", async () => {
    mockTouch(true);
    await makeMockEnv();
    keyDown("a");
    expect(published()).toBe("touch");
    keyDown("Tab");
    expect(published()).toBe("keyboard");
    expect(getService("ui").inputModality).toBe("keyboard");
    expect(document.body).not.toHaveClass("o_touch_device");
});

test("subscribers hear a change, and only a change", async () => {
    await makeMockEnv();
    const heard = [];
    const unsubscribe = inputModality.subscribe((modality) => heard.push(modality));
    pointerDown("mouse");
    pointerDown("touch");
    pointerDown("touch");
    keyDown("ArrowDown");
    unsubscribe();
    pointerDown("mouse");
    expect(heard).toEqual(["touch", "keyboard"]);
});

test("a component re-renders when the modality changes", async () => {
    class Probe extends Component {
        static props = {};
        static template = xml`<span class="probe" t-out="this.modality.current"/>`;
        setup() {
            this.modality = useInputModality();
        }
    }
    await mountWithCleanup(Probe);
    expect(".probe").toHaveText("mouse");
    pointerDown("touch");
    await animationFrame();
    expect(".probe").toHaveText("touch");
});

test("hover capability is the device's, not the modality's", async () => {
    mockMatchMedia({ hover: "none" });
    await makeMockEnv();
    pointerDown("mouse");
    expect(getService("ui").canHover).toBe(false);
});

test("setInputModality puts a test in a modality", async () => {
    await makeMockEnv();
    setInputModality("touch");
    expect(published()).toBe("touch");
    expect(document.body).toHaveClass("o_touch_device");
});

class HitTargets extends Component {
    static props = {};
    static template = xml`
        <div class="o_web_client">
            <button class="btn btn-primary o_text">Save</button>
            <button class="btn btn-secondary o_icon"><i class="fa fa-fw fa-cog"/></button>
            <div class="dropdown-menu show"><a class="dropdown-item" href="#">Item</a></div>
        </div>`;
}

test("under touch a button, an icon button and a menu item are at least 44px", async () => {
    await mountWithCleanup(HitTargets);
    setInputModality("touch");
    await animationFrame();
    expect(queryRect(".o_text").height).toBeGreaterThan(43.5);
    expect(queryRect(".o_icon").height).toBeGreaterThan(43.5);
    expect(queryRect(".o_icon").width).toBeGreaterThan(43.5);
    expect(queryRect(".dropdown-item").height).toBeGreaterThan(43.5);
});

test("a mouse keeps the dense sizes", async () => {
    await mountWithCleanup(HitTargets);
    setInputModality("mouse");
    await animationFrame();
    expect(queryRect(".o_text").height).toBeLessThan(44);
});
