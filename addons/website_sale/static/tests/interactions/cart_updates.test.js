import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import { browser } from "@web/core/browser/browser";

setupInteractionWhiteList("website_sale.cart_updates");
describe.current.tags("interaction_dev");

const page = `
    <header>
        <li class="o_wsale_my_cart"><sup class="my_cart_quantity">1</sup></li>
    </header>
    <div class="oe_website_sale"><div class="oe_cart col-lg-7"></div></div>`;

test("the cart's update event refreshes the header badge and shows the warning", async () => {
    await startInteractions(page);

    document.dispatchEvent(
        new CustomEvent("website_sale:cart_updated", {
            detail: {
                cart_quantity: 4,
                cart_ready: true,
                warning: "Only 4 left",
                quick_reorder: false,
            },
        }),
    );
    await advanceTime(300);
    await animationFrame();

    expect(".my_cart_quantity").toHaveText("4");
    expect(browser.sessionStorage.getItem("website_sale_cart_quantity")).toBe("4");
    expect("#data_warning").toHaveText("Only 4 left");
});
