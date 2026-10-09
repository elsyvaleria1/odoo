// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { click, queryAll, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, xml } from "@odoo/owl";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { applyFragments } from "@web/public/fragments";
import { Interaction } from "@web/public/interaction";

import { startInteraction } from "./helpers.js";

describe.current.tags("interaction_dev");

/**
 * @param {string} key
 * @param {string} html
 * @param {"morph" | "inner" | "outer"} [swap]
 */
function fragment(key, html, swap = "morph") {
    return { key, html, swap };
}

/**
 * @param {Partial<import("@web/public/fragments").FragmentResponse>} response
 * @returns {import("@web/public/fragments").FragmentResponse}
 */
function response({ fragments = [], events = [], redirect = null, data = {} } = {}) {
    return { fragments, events, redirect, data };
}

const cart = (lines) =>
    `<ul data-fragment="cart.lines">${lines
        .map((name) => `<li class="line" data-name="${name}">${name}</li>`)
        .join("")}</ul>`;

test("restarts the interactions inside the target once and leaves the others alone", async () => {
    const steps = [];
    class Line extends Interaction {
        static selector = ".line";
        setup() {
            steps.push(`start ${this.el.dataset.name}`);
        }
        destroy() {
            steps.push(`stop ${this.el.dataset.name}`);
        }
    }
    const { core } = await startInteraction(
        Line,
        `<div>${cart(["a", "b"])}<li class="line" data-name="outside"></li></div>`,
    );
    steps.length = 0;

    applyFragments(
        response({ fragments: [fragment("cart.lines", cart(["a", "c"]))] }),
        {
            interactions: core,
        },
    );
    await animationFrame();

    expect(steps).toEqual(["stop b", "stop a", "start a", "start c"]);
    expect(queryAll(".line").map((el) => el.dataset.name)).toEqual([
        "a",
        "c",
        "outside",
    ]);
});

test("an interaction around the target listens to the nodes the swap added", async () => {
    const clicked = [];
    class Cart extends Interaction {
        static selector = ".cart";
        dynamicContent = {
            ".line": {
                "t-on-click": (ev) => clicked.push(ev.currentTarget.dataset.name),
            },
        };
    }
    const { core } = await startInteraction(
        Cart,
        `<div class="cart">${cart(["a"])}</div>`,
    );

    applyFragments(
        response({ fragments: [fragment("cart.lines", cart(["a", "b"]))] }),
        {
            interactions: core,
        },
    );
    await click(".line[data-name=b]");
    await click(".line[data-name=a]");

    expect(clicked).toEqual(["b", "a"]);
});

test("swaps every element carrying the key", async () => {
    const { core } = await startInteraction(
        [],
        `<span data-fragment="cart.total">1</span><p>x</p><span data-fragment="cart.total">1</span>`,
    );

    applyFragments(
        response({
            fragments: [
                fragment("cart.total", `<span data-fragment="cart.total">9</span>`),
            ],
        }),
        { interactions: core },
    );

    expect(
        queryAll("[data-fragment='cart.total']").map((el) => el.textContent),
    ).toEqual(["9", "9"]);
});

test("the field being typed in keeps its value, focus and caret", async () => {
    const form = (qty, total) =>
        `<form data-fragment="cart.form"><input id="qty" value="${qty}"/><b>${total}</b></form>`;
    const { core } = await startInteraction([], form(1, 10));
    const input = /** @type {HTMLInputElement} */ (queryOne("#qty"));
    input.focus();
    input.value = "12";
    input.setSelectionRange(2, 2);

    applyFragments(response({ fragments: [fragment("cart.form", form(5, 50))] }), {
        interactions: core,
    });

    expect(queryOne("#qty")).toBe(input);
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("12");
    expect(input.selectionStart).toBe(2);
    expect("b").toHaveText("50");
});

test("DOM an interaction inserted is not duplicated by the swap", async () => {
    class Badge extends Interaction {
        static selector = "[data-fragment='cart.lines']";
        start() {
            const badge = document.createElement("i");
            badge.className = "badge";
            this.insert(badge);
        }
    }
    const { core } = await startInteraction(Badge, cart(["a"]));

    applyFragments(
        response({ fragments: [fragment("cart.lines", cart(["a", "b"]))] }),
        {
            interactions: core,
        },
    );
    await animationFrame();

    expect(".badge").toHaveCount(1);
    expect(".line").toHaveCount(2);
});

test("an OWL component mounted inside the target is mounted once after the swap", async () => {
    class Counter extends Component {
        static template = xml`<em class="counter">component</em>`;
        static props = {};
    }
    class Host extends Interaction {
        static selector = "[data-fragment='cart.lines']";
        start() {
            this.mountComponent(this.el, Counter);
        }
    }
    const { core } = await startInteraction(Host, cart(["a"]));
    await animationFrame();
    expect(".counter").toHaveCount(1);

    applyFragments(
        response({ fragments: [fragment("cart.lines", cart(["a", "b"]))] }),
        {
            interactions: core,
        },
    );
    await animationFrame();

    expect(".counter").toHaveCount(1);
    expect(".line").toHaveCount(2);
});

test("an interaction may swap the fragment that holds it", async () => {
    class Remove extends Interaction {
        static selector = ".remove";
        dynamicContent = {
            _root: {
                "t-on-click": () =>
                    this.swapFragments(
                        response({
                            fragments: [fragment("cart.lines", cart(["a"]))],
                            data: { quantity: 1 },
                        }),
                    ),
            },
        };
    }
    await startInteraction(
        Remove,
        `<ul data-fragment="cart.lines"><li class="line">a</li><li class="line">b<button class="remove">x</button></li></ul>`,
    );

    await click(".remove");
    await animationFrame();

    expect(".line").toHaveCount(1);
    expect(".remove").toHaveCount(0);
});

test("events fire after every swap, on document, and the data is returned", async () => {
    const { core } = await startInteraction([], cart(["a"]));
    document.addEventListener(
        "cart:updated",
        (ev) =>
            expect.step(
                `${/** @type {CustomEvent} */ (ev).detail.quantity} ${queryAll(".line").length}`,
            ),
        { once: true },
    );

    const data = applyFragments(
        response({
            fragments: [fragment("cart.lines", cart(["a", "b"]))],
            events: [{ name: "cart:updated", detail: { quantity: 2 } }],
            data: { quantity: 2 },
        }),
        { interactions: core },
    );

    expect.verifySteps(["2 2"]);
    expect(data).toEqual({ quantity: 2 });
});

test("follows the redirect after the swap", async () => {
    patchWithCleanup(browser.location, {
        assign: (url) => expect.step(`assign ${url} ${queryAll(".line").length}`),
    });
    const { core } = await startInteraction([], cart(["a"]));

    applyFragments(
        response({
            fragments: [fragment("cart.lines", cart(["a", "b"]))],
            redirect: "/shop/checkout",
        }),
        { interactions: core },
    );

    expect.verifySteps(["assign /shop/checkout 2"]);
});

test("outer replaces the target, inner keeps it and its attributes", async () => {
    const { core } = await startInteraction(
        [],
        `<div data-fragment="a" class="old">1</div><div data-fragment="b" class="old">1</div>`,
    );
    const [a, b] = queryAll("[data-fragment]");

    applyFragments(
        response({
            fragments: [
                fragment("a", `<div data-fragment="a" class="new">2</div>`, "outer"),
                fragment("b", `<div data-fragment="b" class="new">2</div>`, "inner"),
            ],
        }),
        { interactions: core },
    );

    expect(queryOne("[data-fragment=a]")).not.toBe(a);
    expect("[data-fragment=a]").toHaveClass("new");
    expect(queryOne("[data-fragment=b]")).toBe(b);
    expect(b).toHaveClass("old");
    expect(b).toHaveText("2");
});

test("a key with no element on the page is skipped", async () => {
    const { core } = await startInteraction([], `<p>nothing to swap</p>`);

    const data = applyFragments(
        response({
            fragments: [fragment("cart.lines", cart(["a"]))],
            data: { quantity: 1 },
        }),
        { interactions: core },
    );

    expect(data).toEqual({ quantity: 1 });
    expect(".line").toHaveCount(0);
});
