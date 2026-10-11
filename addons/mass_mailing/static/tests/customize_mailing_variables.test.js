import { CustomizeMailingPlugin } from "@mass_mailing/builder/plugins/customize_mailing_plugin";
import {
    CUSTOMIZE_MAILING_VARIABLES,
    CUSTOMIZE_MAILING_VARIABLES_DEFAULTS,
} from "@mass_mailing/builder/plugins/customize_mailing_variables";
import { expect, test } from "@odoo/hoot";
import { ICON_CLASS_SELECTOR } from "@web/core/utils/icons";

const KNOWN_INTENTIONAL_GAPS = [
    "--btn-primary-font-style",
    "--btn-primary-font-weight",
    "--btn-primary-text-decoration-line",
    "--btn-secondary-font-style",
    "--btn-secondary-font-weight",
    "--btn-secondary-text-decoration-line",
];

test("every CUSTOMIZE_MAILING_VARIABLES key has a matching CUSTOMIZE_MAILING_VARIABLES_DEFAULTS entry", () => {
    const missing = Object.keys(CUSTOMIZE_MAILING_VARIABLES).filter(
        (key) =>
            !(key in CUSTOMIZE_MAILING_VARIABLES_DEFAULTS) &&
            !KNOWN_INTENTIONAL_GAPS.includes(key),
    );
    expect(missing).toEqual([]);
});

test("a link wrapping an icon of any spelling is not styled as a text link", () => {
    const [linkSelector] = CUSTOMIZE_MAILING_VARIABLES["--link-color"].selectors;
    const container = document.createElement("div");
    container.innerHTML = `
        <a class="o_text" href="#">text</a>
        <a class="o_fa7" href="#"><span class="fa-brands fa-facebook"></span></a>
        <a class="o_fa4" href="#"><i class="fa fa-star"></i></a>
        <a class="o_oi" href="#"><i class="oi oi-arrow-right"></i></a>
    `;
    const matched = [...container.querySelectorAll(linkSelector)].map(
        (el) => el.className,
    );
    expect(matched).toEqual(["o_text"]);
});

test("the link selector reads back from a stylesheet unchanged", () => {
    const [linkSelector] = CUSTOMIZE_MAILING_VARIABLES["--link-color"].selectors;
    const sheet = new CSSStyleSheet();
    sheet.insertRule(`${linkSelector} { }`);
    expect(sheet.cssRules[0].selectorText).toBe(linkSelector);
});

test("a font family never reaches an icon, and a saved exclusion is upgraded once", () => {
    const transform = (selector) =>
        CustomizeMailingPlugin.prototype.transformFontFamilySelector.call(
            null,
            selector,
        );
    const exclude = `:not(${ICON_CLASS_SELECTOR})`;
    expect(transform(".o_mail_wrapper p")).toEqual([
        `.o_mail_wrapper p${exclude}`,
        `.o_mail_wrapper p *${exclude}`,
    ]);
    for (const saved of [
        `* :not(.fa)`,
        `* :not(.fa-solid, .fa-regular, .fa-brands, .oi)`,
        `* ${exclude}`,
    ]) {
        expect(transform(saved)).toEqual([`* ${exclude}`], { message: saved });
    }
    expect(transform(`p:not(.o_keep)`)).toEqual([
        `p:not(.o_keep)${exclude}`,
        `p:not(.o_keep) *${exclude}`,
    ]);
});
