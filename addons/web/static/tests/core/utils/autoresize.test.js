// @ts-check

import { expect, test } from "@odoo/hoot";
import { queryOne, queryRect } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { contains, mountWithCleanup } from "@web/../tests/web_test_helpers";
import { resizeTextArea, useAutoresize } from "@web/core/utils/dom/autoresize";
import { elementRef } from "@web/core/utils/element_ref";

test(`resizable input`, async () => {
    class ResizableInput extends Component {
        static template = xml`<input class="resizable-input" t-ref="this.inputRef"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            this.inputRef = elementRef(HTMLInputElement);
            useAutoresize(this.inputRef);
        }
    }
    await mountWithCleanup(ResizableInput);
    const initialWidth = queryRect(`.resizable-input`).width;

    await contains(`.resizable-input`).edit("new value");
    expect(`.resizable-input`).not.toHaveRect({ width: initialWidth });
});

test(`resizable textarea`, async () => {
    class ResizableTextArea extends Component {
        static template = xml`<textarea class="resizable-textarea" t-ref="this.textareaRef"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            this.textareaRef = elementRef(HTMLTextAreaElement);
            useAutoresize(this.textareaRef);
        }
    }
    await mountWithCleanup(ResizableTextArea);
    const initialHeight = queryRect(`.resizable-textarea`).height;

    await contains(`.resizable-textarea`).edit("new value\n".repeat(5));
    expect(`.resizable-textarea`).not.toHaveRect({ height: initialHeight });
});

test(`resizable textarea with minimum height`, async () => {
    class ResizableTextArea extends Component {
        static template = xml`<textarea class="resizable-textarea" t-ref="this.textareaRef"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            this.textareaRef = elementRef(HTMLTextAreaElement);
            useAutoresize(this.textareaRef, { minimumHeight: 100 });
        }
    }
    await mountWithCleanup(ResizableTextArea);
    const initialHeight = queryRect(`.resizable-textarea`).height;
    expect(initialHeight).toBe(100);

    await contains(`.resizable-textarea`).edit("new value\n".repeat(5));
    expect(`.resizable-textarea`).not.toHaveRect({ height: initialHeight });
});

test(`call onResize callback`, async () => {
    class ResizableInput extends Component {
        static template = xml`<input class="resizable-input" t-ref="this.inputRef"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            /** @type {import("@odoo/owl").Ref<HTMLInputElement>} */
            const inputRef = (this.inputRef = elementRef(HTMLInputElement));
            useAutoresize(inputRef, {
                minimumHeight: 10,
                onResize(el, options) {
                    expect.step("onResize");
                    expect(el).toBe(inputRef.el);
                    expect(options).toInclude("minimumHeight");
                },
            });
        }
    }
    await mountWithCleanup(ResizableInput);
    expect.verifySteps(["onResize"]);

    await contains(`.resizable-input`).edit("new value", { instantly: true });
    expect.verifySteps(["onResize"]);
});

test(`call onResize callback after resizing text area`, async () => {
    class ResizableTextArea extends Component {
        static template = xml`<textarea class="resizable-textarea" t-ref="this.textareaRef"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            /** @type {import("@odoo/owl").Ref<HTMLTextAreaElement>} */
            const textareaRef = (this.textareaRef = elementRef(HTMLTextAreaElement));
            useAutoresize(textareaRef, {
                onResize(el, options) {
                    expect.step("onResizeTextArea");
                },
            });
        }
    }
    await mountWithCleanup(ResizableTextArea);
    expect.verifySteps(["onResizeTextArea"]);

    const target = queryOne(".resizable-textarea");
    target.style.width = `500px`;
    await animationFrame();
    expect.verifySteps(["onResizeTextArea"]);
});

function makeStyledTextArea(inlineCss = "") {
    const host = document.createElement("div");
    const styleEl = document.createElement("style");
    styleEl.textContent =
        ".probe-ta { padding: 7px 3px; border: 2px solid red; box-sizing: border-box; }";
    const ta = document.createElement("textarea");
    ta.className = "probe-ta";
    ta.style.cssText = inlineCss;
    ta.value = "one\ntwo\nthree";
    host.append(styleEl, ta);
    document.body.appendChild(host);
    return { host, ta };
}

test("resizeTextArea leaves no inline padding/border of its own", () => {
    const { host, ta } = makeStyledTextArea();
    resizeTextArea(ta);
    const padding = ta.style.padding;
    const borderTop = ta.style.borderTopWidth;
    host.remove();
    expect(padding).toBe("");
    expect(borderTop).toBe("");
});

test("resizeTextArea preserves an author's inline padding", () => {
    const { host, ta } = makeStyledTextArea("padding: 11px;");
    resizeTextArea(ta);
    const padding = ta.style.padding;
    host.remove();
    expect(padding).toBe("11px");
});

test("resizeTextArea preserves an author's inline padding longhand", () => {
    const { host, ta } = makeStyledTextArea("padding-top: 9px;");
    resizeTextArea(ta);
    const top = ta.style.paddingTop;
    const bottom = ta.style.paddingBottom;
    host.remove();
    expect(top).toBe("9px");
    expect(bottom).toBe("");
});

test("resizeTextArea still applies a height", () => {
    const { host, ta } = makeStyledTextArea();
    resizeTextArea(ta, { minimumHeight: 123 });
    const height = ta.style.height;
    host.remove();
    expect(Number.parseFloat(height)).toBeGreaterThan(0);
});

test("a re-render that changes nothing does not swallow the next real resize", async () => {
    class Host extends Component {
        static template = xml`
            <div class="host" t-att-data-renders="this.state.renders" style="width: 400px">
                <textarea class="resizable-textarea" style="width: 100%" t-ref="this.textareaRef"/>
            </div>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({ renders: 0 });
            this.textareaRef = elementRef(HTMLTextAreaElement);
            useAutoresize(this.textareaRef);
        }
    }
    const host = await mountWithCleanup(Host);
    const textarea = /** @type {HTMLTextAreaElement} */ (
        queryOne(".resizable-textarea")
    );
    textarea.value = "word ".repeat(12);
    textarea.dispatchEvent(new Event("input"));
    await animationFrame();
    await animationFrame();
    const oneLine = queryRect(".resizable-textarea").height;

    host.state.renders++;
    await animationFrame();
    await animationFrame();
    expect(".resizable-textarea").toHaveRect({ height: oneLine });

    /** @type {HTMLElement} */ (queryOne(".host")).style.width = "60px";
    await animationFrame();
    await animationFrame();
    await animationFrame();
    const needed = textarea.scrollHeight;
    expect(needed).toBeGreaterThan(oneLine);
    expect(queryRect(".resizable-textarea").height).toBeGreaterThan(oneLine);
});
