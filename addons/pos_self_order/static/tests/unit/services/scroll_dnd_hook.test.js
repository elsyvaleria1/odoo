import { describe, expect, test } from "@odoo/hoot";
import { Component, useProps, xml } from "@odoo/owl";
import { useDraggableScroll } from "@pos_self_order/app/utils/scroll_dnd_hook";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { elementRef } from "@web/core/utils/element_ref";

import { definePosSelfModels } from "../data/generate_model_definitions.js";
import { setupSelfPosEnv } from "../utils.js";

definePosSelfModels();

const setupComponent = async () => {
    await setupSelfPosEnv();
    class TestComponent extends Component {
        static template = xml`<div style="width: 200px; overflow-x: auto;" t-ref="this.scrollRef">
            <div style="width: 1000px; height: 20px;">Scrollable Content</div>
        </div>`;
        static props = {};
        props = useProps(this.constructor.props);
        setup() {
            this.scrollRef = elementRef();
            useDraggableScroll(this.scrollRef);
        }
    }

    const comp = await mountWithCleanup(TestComponent, {});
    const scrollEl = comp.scrollRef.el;
    const dispatchEvent = (type, clientX, opts) => {
        scrollEl.dispatchEvent(
            new MouseEvent(type, {
                bubbles: true,
                clientX: clientX,
                ...opts,
            }),
        );
    };
    return { comp, scrollEl, dispatchEvent };
};

describe("useDraggableScroll", () => {
    test.tags("desktop");
    test("drags and scrolls horizontally", async () => {
        const { scrollEl, dispatchEvent } = await setupComponent();
        dispatchEvent("mousedown", 800);
        dispatchEvent("mousemove", 500);
        dispatchEvent("mouseup");
        expect(scrollEl.scrollLeft).toBeGreaterThan(0);
    });

    test.tags("desktop");
    test("does not scroll if movement is less than threshold", async () => {
        const { scrollEl, dispatchEvent } = await setupComponent();

        dispatchEvent("mousedown", 500);
        dispatchEvent("mousemove", 500 + 2);
        dispatchEvent("mouseup");
        expect(scrollEl.scrollLeft).toBe(0);
    });
});
