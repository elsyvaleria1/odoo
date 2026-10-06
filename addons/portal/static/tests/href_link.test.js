import { expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { HrefLink } from "@portal/interactions/href_link";
import { startInteraction } from "@web/../tests/public/helpers";
import { browser } from "@web/core/browser/browser";

test("a click on the container follows its href", async () => {
    await startInteraction(
        HrefLink,
        `<table><tr class="row-link" data-o-href="/profile/user/7"><td class="cell">Mitchell</td></tr></table>`,
    );
    await click(".cell");
    expect(browser.location.pathname).toBe("/profile/user/7");
});

test("a nested link or button keeps its own action", async () => {
    await startInteraction(
        HrefLink,
        `<div class="card-body" data-o-href="/slides/course-1">
            <a class="tag" href="/slides/tag/furniture-3">Tag</a>
            <button class="download" type="button"><i class="icon">x</i></button>
        </div>`,
    );
    document
        .querySelector(".tag")
        .addEventListener("click", (ev) => ev.preventDefault());
    const before = browser.location.href;
    await click(".icon");
    await click(".tag");
    expect(browser.location.href).toBe(before);
});

test("a button carrying the href prevents the enclosing link", async () => {
    await startInteraction(
        HrefLink,
        `<a class="result" href="/shop/product-1">
            <button type="button" class="category" data-o-href="/shop/category/desks-2">Desks</button>
        </a>`,
    );
    let prevented;
    document.querySelector(".result").addEventListener("click", (ev) => {
        prevented = ev.defaultPrevented;
        ev.preventDefault();
    });
    await click(".category");
    expect(prevented).toBe(true);
    expect(browser.location.pathname).toBe("/shop/category/desks-2");
});

test("an unsafe scheme is not followed", async () => {
    await startInteraction(
        HrefLink,
        `<div class="box" data-o-href="javascript:alert(1)">Box</div>`,
    );
    const before = browser.location.href;
    await click(".box");
    expect(browser.location.href).toBe(before);
});
