import { after, beforeEach, describe, expect, test } from "@odoo/hoot";
import { click, queryOne } from "@odoo/hoot-dom";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import {
    defineWebModels,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

setupInteractionWhiteList("website_sale.cart_line");
describe.current.tags("interaction_dev");
beforeEach(defineWebModels);

/** @param {number} quantity */
const cartLines = (quantity) => `
    <div class="d-contents" data-fragment="website_sale.cart_lines">
        <div id="cart_products" class="js_cart_lines">
            <div class="o_cart_product" data-product-id="1">
                <div class="css_quantity">
                    <input class="js_quantity" data-line-id="7" data-product-id="1" value="${quantity}"/>
                </div>
                <span class="line_total">${quantity * 10}</span>
                <button class="js_delete_product">Remove</button>
            </div>
        </div>
    </div>`;

/** @param {string} classes */
const total = (amount, classes) =>
    `<div class="o_cart_total ${classes}" data-fragment="website_sale.total"><b class="amount">${amount}</b></div>`;

const page = () => `
    <div id="shop_cart">
        <span><button id="quick_reorder_button" disabled="true">Quick reorder</button></span>
        ${cartLines(1)}
        ${total(10, "o_checkout_cart_total pt-2")}
    </div>`;

test("the quantity field keeps focus while the cart lines and the total are swapped", async () => {
    onRpc("/shop/cart/update", async (request) => {
        const { params } = JSON.parse(
            new TextDecoder("utf-8").decode(await request.arrayBuffer()),
        );
        expect.step(`update ${params.line_id} ${params.quantity}`);
        return {
            fragments: [
                { key: "website_sale.cart_lines", html: cartLines(3), swap: "morph" },
                { key: "website_sale.total", html: total(30, ""), swap: "inner" },
            ],
            events: [],
            redirect: null,
            data: { quantity: 3, cart_quantity: 3, cart_ready: true },
        };
    });
    await startInteractions(page());
    const input = queryOne(".js_quantity");
    input.focus();
    input.value = "3";
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await advanceTime(500);
    await animationFrame();

    expect.verifySteps(["update 7 3"]);
    expect(queryOne(".js_quantity")).toBe(input);
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("3");
    expect(".line_total").toHaveText("30");
    expect(".o_cart_total").toHaveText("30");
    expect(".o_cart_total").toHaveClass(["o_checkout_cart_total", "pt-2"]);
});

test("the server's quantity replaces what was typed in the focused field", async () => {
    onRpc("/shop/cart/update", () => ({
        fragments: [
            { key: "website_sale.cart_lines", html: cartLines(5), swap: "morph" },
        ],
        events: [],
        redirect: null,
        data: { quantity: 5, cart_quantity: 5, cart_ready: true },
    }));
    await startInteractions(page());
    const input = queryOne(".js_quantity");
    input.focus();
    input.value = "99";
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await advanceTime(500);
    await animationFrame();

    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("5");
});

test("emptying the cart follows the server's redirect", async () => {
    patchWithCleanup(browser.location, {
        assign: (url) => expect.step(`assign ${url}`),
    });
    onRpc("/shop/cart/update", () => ({
        fragments: [],
        events: [
            {
                name: "website_sale:cart_updated",
                detail: { cart_quantity: 0, cart_ready: false, warning: "" },
            },
        ],
        redirect: "/shop/cart",
        data: { quantity: 0 },
    }));
    const listener = (ev) => expect.step(`cart ${ev.detail.cart_quantity}`);
    document.addEventListener("website_sale:cart_updated", listener);
    after(() => document.removeEventListener("website_sale:cart_updated", listener));
    await startInteractions(page());

    await click(".js_delete_product");
    await animationFrame();

    expect.verifySteps(["cart 0", "assign /shop/cart"]);
});
