// @ts-check

import { after, describe, expect, getFixture, test } from "@odoo/hoot";
import { click, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { FragmentShell } from "@web/public/fragment_shell";

describe.current.tags("headless");

/** @param {string} items */
const list = (items) => `
    <section data-fragment="app.list">
        <ul>${items}</ul>
        <a class="o_next" href="/app/list?page=2">Next</a>
        <a class="o_out" href="/elsewhere" data-no-fragment="">Out</a>
        <form class="o_add" method="post" action="/app/add">
            <input name="name" value="New"/>
            <button type="submit">Add</button>
        </form>
    </section>`;

/**
 * @param {string} html
 * @param {import("@web/public/fragment_shell").ShellOptions} [options]
 */
function startShell(html, options = {}) {
    const fixture = /** @type {HTMLElement} */ (getFixture());
    fixture.innerHTML = `<div id="app">${html}</div>`;
    const shell = new FragmentShell(/** @type {HTMLElement} */ (queryOne("#app")), {
        headers: () => ({ "X-Telegram-Init-Data": "init" }),
        ...options,
    });
    shell.start();
    after(() => shell.stop());
    patchWithCleanup(window.history, {
        pushState: (_state, _title, url) =>
            expect.step(
                `push ${new URL(String(url)).pathname}${new URL(String(url)).search}`,
            ),
        replaceState: () => {},
    });
    return shell;
}

/**
 * @param {(url: URL, init: RequestInit) => { status?: number, json?: any, html?: string, url?: string }} answer
 */
function serve(answer) {
    patchWithCleanup(window, {
        fetch: async (url, init = {}) => {
            const target = new URL(String(url), window.location.href);
            const headers = /** @type {Record<string, string>} */ (init.headers);
            expect.step(
                `${init.method || "GET"} ${target.pathname}${target.search} ${headers["X-Telegram-Init-Data"]}`,
            );
            const { status = 200, json, html, url: answered } = answer(target, init);
            return /** @type {Response} */ ({
                ok: status < 400,
                status,
                url: answered || target.href,
                headers: new Headers({
                    "Content-Type": json ? "application/json" : "text/html",
                }),
                json: async () => json,
                text: async () => html || "",
            });
        },
    });
}

test("a link visits the page in place with the shell's headers", async () => {
    const lang = document.documentElement.lang;
    after(() => {
        document.documentElement.lang = lang;
    });
    startShell(list("<li>a</li>"));
    serve(() => ({
        html: `<html lang="es-MX"><head><title>Page 2</title></head><body>${list("<li>b</li>")}</body></html>`,
    }));
    const section = queryOne("[data-fragment='app.list']");

    await click(".o_next");
    await animationFrame();

    expect.verifySteps(["GET /app/list?page=2 init", "push /app/list?page=2"]);
    expect(queryOne("[data-fragment='app.list']")).toBe(section);
    expect("li").toHaveText("b");
    expect(document.title).toBe("Page 2");
    expect(document.documentElement.lang).toBe("es-MX");
});

test("a page without the shell's regions is left to the browser", async () => {
    const shell = startShell(list("<li>a</li>"));
    serve(() => ({ html: "<html><body><p>Backend</p></body></html>" }));
    patchWithCleanup(shell, {
        leave: (url) => expect.step(`leave ${new URL(url).pathname}`),
    });

    await click(".o_next");
    await animationFrame();

    expect.verifySteps(["GET /app/list?page=2 init", "leave /app/list"]);
    expect("li").toHaveText("a");
});

test("a link marked data-no-fragment is left to the browser", async () => {
    startShell(list(""));
    serve(() => ({ html: "" }));
    const prevent = (ev) => ev.preventDefault();
    document.addEventListener("click", prevent);
    after(() => document.removeEventListener("click", prevent));

    await click(".o_out");
    await animationFrame();

    expect.verifySteps([]);
});

test("a form posts with its headers and swaps the fragments it answers", async () => {
    startShell(list("<li>a</li>"));
    serve(() => ({
        json: {
            fragments: [
                {
                    key: "app.list",
                    html: list("<li>a</li><li>New</li>"),
                    swap: "morph",
                },
            ],
            events: [{ name: "app:added", detail: { name: "New" } }],
            redirect: null,
            data: {},
        },
    }));
    const listener = (ev) => expect.step(`event ${ev.detail.name}`);
    document.addEventListener("app:added", listener);
    after(() => document.removeEventListener("app:added", listener));

    await click(".o_add button");
    await animationFrame();

    expect.verifySteps(["POST /app/add init", "event New"]);
    expect("li").toHaveCount(2);
});

test("a form whose route redirects takes the page it lands on", async () => {
    startShell(list("<li>a</li>"));
    serve(() => ({
        html: `<html><body>${list("<li>a</li><li>New</li>")}</body></html>`,
        url: "http://localhost/app/list?added=1",
    }));

    await click(".o_add button");
    await animationFrame();

    expect.verifySteps(["POST /app/add init", "push /app/list?added=1"]);
    expect("li").toHaveCount(2);
});

test("a refusal goes to onRefused and changes nothing", async () => {
    startShell(list("<li>a</li>"), {
        onRefused: (message) => expect.step(`refused ${message}`),
    });
    serve(() => ({ status: 403, json: { error: { message: "Not your task" } } }));

    await click(".o_add button");
    await animationFrame();

    expect.verifySteps(["POST /app/add init", "refused Not your task"]);
    expect("li").toHaveCount(1);
});
