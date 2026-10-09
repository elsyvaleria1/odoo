import { describe, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import { browser } from "@web/core/browser/browser";

setupInteractionWhiteList("website.website_page");

describe.current.tags("interaction_dev");

test("a language switch goes through /website/lang with the link's url code", async () => {
    // the selector's links carry `data-url_code` (an underscore key of the
    // dataset); reading a camel-cased key sent every visitor to
    // /website/lang/undefined
    const { core } = await startInteractions(`
        <div id="wrapwrap">
            <div class="js_language_selector">
                <a class="js_change_lang" href="/fr/contact" data-url_code="fr">Français</a>
            </div>
        </div>
    `);
    expect(core.interactions).toHaveLength(1);
    await click(".js_change_lang");
    expect(browser.location.href).toMatch(/\/website\/lang\/fr\?r=%2Ffr%2Fcontact$/);
});

test("after an in-place navigation the language links target the new page", async () => {
    await startInteractions(`
        <div id="wrapwrap">
            <div class="js_language_selector">
                <a class="js_change_lang" href="/fr/shop" data-url_code="fr">Français</a>
                <a class="js_change_lang" href="/shop" data-url_code="en">English</a>
            </div>
        </div>
    `);
    const page = new DOMParser().parseFromString(
        `<html><body>
            <a class="js_change_lang" href="/fr/shop?order=name+asc" data-url_code="fr">Français</a>
            <a class="js_change_lang" href="/shop?order=name+asc" data-url_code="en">English</a>
        </body></html>`,
        "text/html",
    );

    window.dispatchEvent(
        new CustomEvent("o-partial-navigation", {
            detail: { key: "website_sale.products", url: "/shop?order=name+asc", page },
        }),
    );

    expect("[data-url_code=fr]").toHaveAttribute("href", "/fr/shop?order=name+asc");
    expect("[data-url_code=en]").toHaveAttribute("href", "/shop?order=name+asc");
});
