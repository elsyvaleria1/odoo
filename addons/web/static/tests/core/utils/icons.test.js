// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import {
    FONT_AWESOME_SELECTOR,
    ICON_CLASS_SELECTOR,
    ICON_SELECTOR,
    iconClasses,
    isIconElement,
} from "@web/core/utils/icons";

describe.current.tags("headless");

/** @param {string} html */
function element(html) {
    const container = document.createElement("div");
    container.innerHTML = html;
    return /** @type {Element} */ (container.firstElementChild);
}

test("an icon of either Font Awesome spelling or an Odoo icon is an icon", () => {
    for (const html of [
        `<i class="fa fa-star"></i>`,
        `<span class="fa-solid fa-star"></span>`,
        `<i class="fa-regular fa-eye"></i>`,
        `<i class="fa-brands fa-facebook"></i>`,
        `<i class="oi oi-arrow-right"></i>`,
    ]) {
        const icon = element(html);
        expect(isIconElement(icon)).toBe(true, { message: html });
        expect(icon.matches(ICON_SELECTOR)).toBe(true, { message: html });
        expect(icon.matches(ICON_CLASS_SELECTOR)).toBe(true, { message: html });
    }
});

test("a glyph class without a style, another tag or a text node is not an icon", () => {
    for (const html of [
        `<i class="fa-star"></i>`,
        `<div class="fa-solid fa-star"></div>`,
    ]) {
        const node = element(html);
        expect(isIconElement(node)).toBe(false, { message: html });
        expect(node.matches(ICON_SELECTOR)).toBe(false, { message: html });
    }
    expect(isIconElement(document.createTextNode("fa"))).toBe(false);
    expect(isIconElement(null)).toBe(false);
});

test("the class selector reads back from a stylesheet unchanged", () => {
    const sheet = new CSSStyleSheet();
    sheet.insertRule(`a:not(:has(${ICON_CLASS_SELECTOR})) { }`);
    expect(
        sheet.cssRules[0].cssText.startsWith(`a:not(:has(${ICON_CLASS_SELECTOR}))`),
    ).toBe(true);
    expect(ICON_CLASS_SELECTOR.split(", ")).toEqual(
        iconClasses.map((cls) => `.${cls}`),
    );
});

test("a Font Awesome icon of either spelling is one, an Odoo icon is not", () => {
    for (const html of [
        `<i class="fa fa-star"></i>`,
        `<span class="fa-brands fa-x-twitter"></span>`,
    ]) {
        expect(element(html).matches(FONT_AWESOME_SELECTOR)).toBe(true, {
            message: html,
        });
    }
    expect(
        element(`<i class="oi oi-arrow-right"></i>`).matches(FONT_AWESOME_SELECTOR),
    ).toBe(false);
});
