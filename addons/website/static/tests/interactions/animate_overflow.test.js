import { describe, expect, test } from "@odoo/hoot";
import {
    animationFrame,
    manuallyDispatchProgrammaticEvent,
    queryOne,
} from "@odoo/hoot-dom";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";

setupInteractionWhiteList("website.animate_overflow");

describe.current.tags("interaction_dev");

test("animate_overflow adds class during animations", async () => {
    const { core } = await startInteractions(`
        <div id="wrapwrap">
            <div class="o_animate"/>
        </div>
    `);
    expect(core.interactions).toHaveLength(1);
    const htmlEl = document.documentElement;
    expect(htmlEl).not.toHaveClass("o_wanim_overflow_xy_hidden");
    const animatedEl = queryOne(".o_animate");
    animatedEl.classList.add("o_animating");
    await manuallyDispatchProgrammaticEvent(animatedEl, "updatecontent");
    expect(htmlEl).toHaveClass("o_wanim_overflow_xy_hidden");
    animatedEl.classList.remove("o_animating");
    await manuallyDispatchProgrammaticEvent(animatedEl, "updatecontent");
    expect(htmlEl).not.toHaveClass("o_wanim_overflow_xy_hidden");
});

test("animate_overflow always adds class if there are transforms", async () => {
    const { core } = await startInteractions(`
        <div id="wrapwrap">
            <div class="o_animate" style="transform: translateY(10px)"/>
        </div>
    `);
    expect(core.interactions).toHaveLength(1);
    expect(document.documentElement).toHaveClass("o_wanim_overflow_xy_hidden");
});

test("animate_overflow rescans the transforms after a fragment swap", async () => {
    await startInteractions(`
        <div id="wrapwrap">
            <div class="o_region"/>
        </div>
    `);
    expect(document.documentElement).not.toHaveClass("o_wanim_overflow_xy_hidden");
    const region = queryOne(".o_region");
    region.innerHTML = `<div class="o_animate" style="transform: translateY(10px)"></div>`;
    region.dispatchEvent(new CustomEvent("o-fragment-swapped", { bubbles: true }));
    await animationFrame();
    expect(document.documentElement).toHaveClass("o_wanim_overflow_xy_hidden");
});
