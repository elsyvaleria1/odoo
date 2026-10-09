// @ts-check

import { after, describe, expect, test } from "@odoo/hoot";
import { click, edit, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { getService, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { FragmentForm } from "@web/public/fragment_form";

import { startInteraction } from "./helpers.js";

describe.current.tags("interaction_dev");

/** @param {number} quantity */
const line = (quantity) => `
    <form data-fragment="cart.line" data-fragment-form="" method="post" action="/shop/cart/line">
        <input name="csrf_token" type="hidden" value="t0k3n"/>
        <input class="o_qty" name="quantity" value="${quantity}" data-submit-on-change=""/>
        <button class="o_update" type="submit">Update</button>
        <button class="o_remove" type="submit" name="remove" value="1">Remove</button>
    </form>`;

/**
 * @param {(body: FormData) => string | null} answer the line rendered for a
 * post, null for a failing route
 */
function serve(answer) {
    patchWithCleanup(browser, {
        fetch: async (url, init) => {
            const body = /** @type {FormData} */ (init.body);
            expect.step(
                `post ${new URL(String(url)).pathname} ${init.headers["X-Odoo-Fragments"]} ${new URLSearchParams(/** @type {any} */ (body)).toString()}`,
            );
            const html = answer(body);
            return /** @type {Response} */ ({
                ok: html !== null,
                status: html === null ? 500 : 200,
                headers: new Headers({ "Content-Type": "application/json" }),
                json: async () => ({
                    fragments: [{ key: "cart.line", html, swap: "morph" }],
                    events: [],
                    redirect: null,
                    data: {},
                }),
            });
        },
    });
}

/** Records a native submission instead of letting it leave the test page. */
function catchNativeSubmit() {
    const listener = (ev) => {
        if (!ev.defaultPrevented) {
            expect.step("native submit");
            ev.preventDefault();
        }
    };
    document.addEventListener("submit", listener);
    after(() => document.removeEventListener("submit", listener));
}

test("a submit posts the form with the fragments header and swaps the answer in", async () => {
    await startInteraction(FragmentForm, line(1));
    serve((body) => line(Number(body.get("quantity")) + 10));
    const form = queryOne("form");

    await click(".o_update");
    await animationFrame();

    expect.verifySteps(["post /shop/cart/line 1 csrf_token=t0k3n&quantity=1"]);
    expect(queryOne("form")).toBe(form);
    expect(".o_qty").toHaveValue("11");
    expect("form").not.toHaveAttribute("aria-busy");
});

test("the submitter's name and value are posted", async () => {
    await startInteraction(FragmentForm, line(2));
    serve(() => line(0));

    await click(".o_remove");
    await animationFrame();

    expect.verifySteps(["post /shop/cart/line 1 csrf_token=t0k3n&quantity=2&remove=1"]);
});

test("a control named action or method does not hide the form's own", async () => {
    await startInteraction(
        FragmentForm,
        `<form data-fragment="cart.line" data-fragment-form="" method="post" action="/shop/cart/line">
            <input name="method" type="hidden" value="m"/>
            <button class="o_act" type="submit" name="action" value="go">Go</button>
        </form>`,
    );
    serve(() => line(1));

    await click(".o_act");
    await animationFrame();

    expect.verifySteps(["post /shop/cart/line 1 method=m&action=go"]);
});

test("a field marked data-submit-on-change submits the form", async () => {
    await startInteraction(FragmentForm, line(1));
    serve(() => line(3));

    await click(".o_qty");
    await edit("3", { confirm: "blur" });
    await animationFrame();

    expect.verifySteps(["post /shop/cart/line 1 csrf_token=t0k3n&quantity=3"]);
});

test("a submit while the post runs is dropped", async () => {
    await startInteraction(FragmentForm, line(1));
    let release;
    patchWithCleanup(browser, {
        fetch: () => {
            expect.step("post");
            return new Promise((resolve) => {
                release = () =>
                    resolve(
                        /** @type {Response} */ ({
                            ok: true,
                            headers: new Headers({
                                "Content-Type": "application/json",
                            }),
                            json: async () => ({
                                fragments: [
                                    { key: "cart.line", html: line(2), swap: "morph" },
                                ],
                                events: [],
                                redirect: null,
                                data: {},
                            }),
                        }),
                    );
            });
        },
    });
    catchNativeSubmit();

    await click(".o_update");
    expect("form").toHaveAttribute("aria-busy", "true");
    await click(".o_update");
    release();
    await animationFrame();

    expect.verifySteps(["post"]);
    expect(".o_qty").toHaveValue("2");
});

test("a failed post submits the form natively, with its submitter", async () => {
    await startInteraction(FragmentForm, line(1));
    serve(() => null);
    catchNativeSubmit();
    const submitters = [];
    queryOne("form").addEventListener("submit", (ev) =>
        submitters.push(/** @type {SubmitEvent} */ (ev).submitter?.className),
    );

    await click(".o_remove");
    await animationFrame();

    expect.verifySteps([
        "post /shop/cart/line 1 csrf_token=t0k3n&quantity=1&remove=1",
        "native submit",
    ]);
    expect(submitters).toEqual(["o_remove", "o_remove"]);
});

test("a get form is left alone", async () => {
    await startInteraction(
        FragmentForm,
        line(1).replace('method="post"', 'method="get"'),
    );
    serve(() => line(1));
    catchNativeSubmit();

    await click(".o_update");
    await animationFrame();

    expect.verifySteps(["native submit"]);
});

/** @param {string} body */
const questionPage = (body) =>
    `<html><head><title>Question</title></head><body><div id="wrapwrap">${question(body)}</div></body></html>`;

/** @param {string} comments */
const question = (comments) => `
    <div data-fragment="forum.question">
        <ul class="o_comments">${comments}</ul>
        <form data-fragment-form="" method="post" action="/forum/1/comment/7/delete">
            <input name="csrf_token" type="hidden" value="t0k3n"/>
            <button class="o_delete" type="submit">Delete</button>
        </form>
    </div>`;

/**
 * @param {string | null} html the page the route redirects to, null for a
 * refusal
 * @param {string} [url]
 */
function redirectTo(html, url = browser.location.href) {
    patchWithCleanup(browser, {
        fetch: async (_url, init) => {
            expect.step(`post ${init.headers["X-Odoo-Partial-Navigation"]}`);
            if (html === null) {
                return /** @type {Response} */ ({
                    ok: false,
                    status: 403,
                    headers: new Headers({ "Content-Type": "application/json" }),
                    json: async () => ({ error: { message: "Not enough karma" } }),
                });
            }
            return /** @type {Response} */ ({
                ok: true,
                status: 200,
                url,
                headers: new Headers({ "Content-Type": "text/html" }),
                text: async () => html,
            });
        },
    });
    patchWithCleanup(browser.location, {
        assign: (target) => expect.step(`assign ${new URL(String(target)).pathname}`),
    });
}

test("a route that redirects to the page shown: the form's region is swapped from it", async () => {
    await startInteraction(FragmentForm, question("<li>one</li><li>two</li>"));
    redirectTo(questionPage("<li>one</li>"));
    const region = queryOne("[data-fragment='forum.question']");

    await click(".o_delete");
    await animationFrame();

    expect.verifySteps(["post forum.question"]);
    expect(queryOne("[data-fragment='forum.question']")).toBe(region);
    expect(".o_comments li").toHaveCount(1);
    expect(document.title).toBe("Question");
});

test("a route that redirects elsewhere loads that page in full", async () => {
    await startInteraction(FragmentForm, question("<li>one</li>"));
    redirectTo(questionPage(""), "http://localhost/forum/1");

    await click(".o_delete");
    await animationFrame();

    expect.verifySteps(["post forum.question", "assign /forum/1"]);
    expect(".o_comments li").toHaveCount(1);
});

test("a refusal shows as a notification and leaves the page as it is", async () => {
    await startInteraction(FragmentForm, question("<li>one</li>"));
    redirectTo(null);
    catchNativeSubmit();
    patchWithCleanup(getService("notification"), {
        add: (message) => {
            expect.step(`notify ${message}`);
            return () => {};
        },
    });

    await click(".o_delete");
    await animationFrame();

    expect.verifySteps(["post forum.question", "notify Not enough karma"]);
    expect(".o_comments li").toHaveCount(1);
});

test("data-confirm asks first: declined posts nothing, accepted posts", async () => {
    await startInteraction(
        FragmentForm,
        question("<li>one</li>").replace(
            'data-fragment-form=""',
            'data-fragment-form="" data-confirm="Delete it?"',
        ),
    );
    redirectTo(questionPage(""));
    let accept = false;
    patchWithCleanup(getService("dialog"), {
        add: (_Dialog, props) => {
            expect.step(`ask ${props.body}`);
            (accept ? props.confirm : props.cancel)();
            return async () => {};
        },
    });

    await click(".o_delete");
    await animationFrame();
    expect.verifySteps(["ask Delete it?"]);

    accept = true;
    await click(".o_delete");
    await animationFrame();
    expect.verifySteps(["ask Delete it?", "post forum.question"]);
    expect(".o_comments li").toHaveCount(0);
});

test("a redirect to the same path with another query swaps in place and shows its URL", async () => {
    await startInteraction(FragmentForm, question("<li>one</li>"));
    redirectTo(questionPage(""), "http://localhost/forum/1/question?access_token=abc");
    patchWithCleanup(browser.location, { href: "http://localhost/forum/1/question" });
    patchWithCleanup(browser.history, {
        replaceState: (_state, _title, url) => expect.step(`replace ${url}`),
    });

    await click(".o_delete");
    await animationFrame();

    expect.verifySteps([
        "post forum.question",
        "replace http://localhost/forum/1/question?access_token=abc",
    ]);
    expect(".o_comments li").toHaveCount(0);
});

test("a submitter's formaction is where the form posts", async () => {
    await startInteraction(
        FragmentForm,
        line(1).replace(
            'class="o_remove" type="submit"',
            'class="o_remove" type="submit" formaction="/shop/cart/line/remove"',
        ),
    );
    serve(() => line(0));

    await click(".o_remove");
    await animationFrame();

    expect.verifySteps([
        "post /shop/cart/line/remove 1 csrf_token=t0k3n&quantity=1&remove=1",
    ]);
});

test("the field just submitted shows the server's value, though focused", async () => {
    await startInteraction(FragmentForm, line(1));
    serve(() => line(10));
    const input = /** @type {HTMLInputElement} */ (queryOne(".o_qty"));
    input.focus();
    input.value = "99";

    input.dispatchEvent(new Event("change", { bubbles: true }));
    await animationFrame();

    expect.verifySteps(["post /shop/cart/line 1 csrf_token=t0k3n&quantity=99"]);
    expect(document.activeElement).toBe(input);
    expect(input).toHaveValue("10");
});
