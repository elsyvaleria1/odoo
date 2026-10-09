// @ts-check

import { describe, expect, getFixture, test } from "@odoo/hoot";
import { markup } from "@odoo/owl";
import { morph } from "@web/core/utils/dom/morph";

describe.current.tags("headless");

/** @param {string} html */
function parse(html) {
    const template = document.createElement("template");
    template.innerHTML = html;
    return template.content;
}

/** @param {string} html */
function mount(html) {
    const fixture = /** @type {HTMLElement} */ (getFixture());
    fixture.innerHTML = html;
    return /** @type {HTMLElement} */ (fixture.firstElementChild);
}

/**
 * @param {Node} root
 * @param {() => void} fn
 */
function mutationsDuring(root, fn) {
    const observer = new MutationObserver(() => {});
    observer.observe(root, {
        subtree: true,
        childList: true,
        attributes: true,
        characterData: true,
    });
    fn();
    const records = observer.takeRecords();
    observer.disconnect();
    return records;
}

test("an identical tree changes nothing", () => {
    const html = `<div class="a"><p id="p">text <b>bold</b></p><ul><li>1</li><li>2</li></ul></div>`;
    const target = mount(html);

    const records = mutationsDuring(getFixture(), () => morph(target, parse(html)));

    expect(records).toHaveLength(0);
});

test("a text change rewrites the text node in place", () => {
    const target = mount(`<div><span>before</span></div>`);
    const textNode = target.querySelector("span").firstChild;

    const records = mutationsDuring(getFixture(), () =>
        morph(target, parse(`<div><span>after</span></div>`)),
    );

    expect(target.querySelector("span").firstChild).toBe(textNode);
    expect(textNode.nodeValue).toBe("after");
    expect(records.map((r) => r.type)).toEqual(["characterData"]);
});

test("outer morph updates the target itself, inner morph only its children", () => {
    const target = mount(`<div class="old"><i>x</i></div>`);

    morph(target, parse(`<div class="new"><i>y</i></div>`));
    expect(getFixture().firstElementChild).toBe(target);
    expect(target).toHaveClass("new");
    expect(target).toHaveText("y");

    morph(target, parse(`<i>z</i>`), { inner: true });
    expect(target).toHaveClass("new");
    expect(target.innerHTML).toBe("<i>z</i>");
});

test("reordered children with ids keep their identity", () => {
    const target = mount(
        `<ul><li id="a">a</li><li id="b">b</li><li id="c">c</li></ul>`,
    );
    const [a, b, c] = target.children;

    morph(
        target,
        parse(`<ul><li id="c">c</li><li id="a">a</li><li id="b">b</li></ul>`),
    );

    expect([...target.children]).toEqual([c, a, b]);
});

test("an element with an id moved to another parent is moved, not recreated", () => {
    const target = mount(
        `<div><section class="one"><input id="qty" value="1"/></section><section class="two"></section></div>`,
    );
    const input = target.querySelector("#qty");

    morph(
        target,
        parse(
            `<div><section class="one"></section><section class="two"><input id="qty" value="1"/></section></div>`,
        ),
    );

    expect(target.querySelector(".two #qty")).toBe(input);
    expect(target.querySelector(".one").children).toHaveLength(0);
});

test("the focused field keeps focus, caret and what the user typed", () => {
    const target = mount(
        `<form><label>Qty</label><input id="qty" name="qty" value="1"/><span class="total">10</span></form>`,
    );
    const input = /** @type {HTMLInputElement} */ (target.querySelector("#qty"));
    input.focus();
    input.value = "123";
    input.setSelectionRange(1, 2);

    morph(
        target,
        parse(
            `<form><p class="warning">Only 5 left</p><label>Qty</label><input id="qty" name="qty" value="5"/><span class="total">50</span></form>`,
        ),
    );

    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("123");
    expect([input.selectionStart, input.selectionEnd]).toEqual([1, 2]);
    expect(input.getAttribute("value")).toBe("5");
    expect(".total").toHaveText("50");
    expect(".warning").toHaveCount(1);
});

test("a field the user is not on takes the server's value and checked state", () => {
    const target = mount(
        `<form><input class="qty" value="1"/><input type="radio" name="m" value="a" checked=""/><input type="radio" name="m" value="b"/></form>`,
    );
    const qty = /** @type {HTMLInputElement} */ (target.querySelector(".qty"));
    const [radioA, radioB] = /** @type {NodeListOf<HTMLInputElement>} */ (
        target.querySelectorAll("[type=radio]")
    );
    qty.value = "7";

    morph(
        target,
        parse(
            `<form><input class="qty" value="2"/><input type="radio" name="m" value="a"/><input type="radio" name="m" value="b" checked=""/></form>`,
        ),
    );

    expect(qty.value).toBe("2");
    expect(radioA.checked).toBe(false);
    expect(radioB.checked).toBe(true);
});

test("a script with different content is replaced, never patched", () => {
    const target = mount(`<div><script type="text/plain">one</script></div>`);
    const script = target.querySelector("script");

    morph(target, parse(`<div><script type="text/plain">two</script></div>`));

    expect(target.querySelector("script")).not.toBe(script);
    expect(target.querySelector("script")).toHaveText("two");
});

test("hooks report each removed node and each new subtree once", () => {
    const target = mount(`<div><p class="keep">k</p><p class="drop">d</p></div>`);
    const steps = [];

    morph(
        target,
        parse(
            `<div><p class="keep">k</p><section><b>new</b><i>also</i></section></div>`,
        ),
        {
            onNodeAdded: (node) => steps.push(`added ${node.nodeName}`),
            onNodeRemoved: (node) => steps.push(`removed ${node.nodeName}`),
        },
    );

    expect(steps).toEqual(["added SECTION", "removed P"]);
});

test("a new subtree built around a kept id is reported once, and the kept node is not", () => {
    const target = mount(`<div><input id="qty"/></div>`);
    const input = target.querySelector("#qty");
    const steps = [];

    morph(target, parse(`<div><section><b>new</b><input id="qty"/></section></div>`), {
        onNodeAdded: (node) => steps.push(`added ${node.nodeName}`),
        onNodeRemoved: (node) => steps.push(`removed ${node.nodeName}`),
    });

    expect(target.querySelector("section #qty")).toBe(input);
    expect(steps).toEqual(["added SECTION"]);
});

test("a kept id the new content drops is reported removed", () => {
    const target = mount(`<div><div><input id="qty"/></div><span>s</span></div>`);
    const steps = [];

    morph(target, parse(`<div><span>s</span></div>`), {
        onNodeRemoved: (node) => steps.push(`removed ${node.nodeName}`),
    });

    expect(target.querySelector("#qty")).toBe(null);
    expect(steps).toEqual(["removed DIV"]);
});

test("leaves nothing behind in the document", () => {
    const target = mount(`<div><p id="x">x</p></div>`);
    const bodySiblings = () => [...document.documentElement.children].length;
    const before = bodySiblings();

    morph(target, parse(`<div><span><p id="x">x</p></span></div>`));

    expect(bodySiblings()).toBe(before);
});

test("a string of any kind is refused: the caller parses what it trusts", () => {
    const target = mount(`<div>safe</div>`);
    const html = "<img src=x onerror=alert(1)>";

    // a plain string, a translated one (_t returns a String subclass) and
    // owl's Markup alike
    for (const content of [html, new String(html), markup(html)]) {
        expect(() => morph(target, /** @type {any} */ (content))).toThrow(TypeError);
    }
    expect(target).toHaveText("safe");
});

test("a kept element marked data-morph-preserve is left as it is", () => {
    const target = mount(
        `<div><p>old</p><div id="chatter" data-morph-preserve="" data-token="a"></div></div>`,
    );
    const chatter = /** @type {HTMLElement} */ (target.querySelector("#chatter"));
    const app = document.createElement("div");
    app.id = "chatterRoot";
    chatter.append(app);

    morph(
        target,
        parse(
            `<div><p>new</p><div id="chatter" data-morph-preserve="" data-token="b"></div></div>`,
        ),
    );

    expect(target.querySelector("p")).toHaveText("new");
    expect(target.querySelector("#chatter")).toBe(chatter);
    expect(chatter.firstElementChild).toBe(app);
    expect(chatter).toHaveAttribute("data-token", "a");
});
