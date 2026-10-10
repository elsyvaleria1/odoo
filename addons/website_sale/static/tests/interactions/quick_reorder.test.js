import { describe, expect, test } from "@odoo/hoot";
import { click, edit, queryAll, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";

setupInteractionWhiteList("website_sale.quick_reorder");
describe.current.tags("interaction_dev");

/** @param {number} id */
const line = (id) => `
    <form class="o_wsale_quick_reorder_line" method="post" action="/shop/cart/quick_add">
        <input type="hidden" name="line_id" value="${id}"/>
        <small class="o_wsale_quick_reorder_product_price">
            <span class="oe_currency_value">2.50</span>
        </small>
        <input name="quantity" value="1" class="o_wsale_quick_reorder_qty_input"
               data-price-unit="2.5" data-currency-digits="2"/>
        <button type="submit" class="o_wsale_quick_reorder_product_button">Add</button>
    </form>`;

const sidebar = `<div id="quick_reorder_sidebar">${line(1)}${line(2)}${line(3)}</div>`;

test("a quantity updates its line's total, and none disables its button", async () => {
    await startInteractions(sidebar);
    const [input] = queryAll(".o_wsale_quick_reorder_qty_input");

    await click(input);
    await edit("4");
    await animationFrame();

    expect(".o_wsale_quick_reorder_line:first .oe_currency_value").toHaveText("10.00");
    expect(".o_wsale_quick_reorder_line:first button").toBeEnabled();

    await edit("0");
    await animationFrame();

    expect(".o_wsale_quick_reorder_line:first button").not.toBeEnabled();
    expect(".o_wsale_quick_reorder_line:first .oe_currency_value").toHaveText("10.00");
});

test("once a line is added, the line now at its place takes the focus", async () => {
    await startInteractions(sidebar);
    const second = queryAll(".o_wsale_quick_reorder_line")[1];
    second.addEventListener("submit", (ev) => ev.preventDefault());

    second.requestSubmit();
    second.remove();
    document.dispatchEvent(
        new CustomEvent("website_sale:cart_updated", {
            detail: { quick_reorder: true },
        }),
    );
    await animationFrame();

    expect(document.activeElement).toBe(
        queryOne(".o_wsale_quick_reorder_line:last .o_wsale_quick_reorder_qty_input"),
    );
});

test("a cart update from elsewhere moves no focus", async () => {
    await startInteractions(sidebar);

    document.dispatchEvent(
        new CustomEvent("website_sale:cart_updated", {
            detail: { quick_reorder: true },
        }),
    );
    await animationFrame();

    expect(document.activeElement).toBe(document.body);
});
