// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { allowTranslations, expectMarkup } from "@web/../tests/web_test_helpers";
import { renderToElement, renderToString } from "@web/core/utils/render";

describe.current.tags("headless");

test("renderToElement always returns an element", () => {
    allowTranslations();
    /** @type {any} */ (renderToString.app).addTemplate(
        "test.render.template.1",
        `<t t-if="False">
          <div>NotOk</div>
        </t>
        <t t-else="">
          <div>Ok</div>
        </t>`,
    );
    const compiledTemplate = renderToElement("test.render.template.1");
    expect(compiledTemplate.parentElement).toBe(null, {
        message: "compiledTemplate.parentElement must be empty",
    });
    expect(compiledTemplate.nodeType).toBe(Node.ELEMENT_NODE, {
        message: "compiledTemplate must be an element",
    });
    expectMarkup(compiledTemplate.outerHTML).toBe("<div>Ok</div>");
});

test("renderToString keeps the form state the template binds as properties", () => {
    /** @type {any} */ (renderToString.app).addTemplate(
        "test.render.template.form_state",
        `<form>
            <input name="name" t-att-value="name"/>
            <input name="on" type="checkbox" t-att-checked="on"/>
            <input name="off" type="checkbox" checked="" t-att-checked="off"/>
            <textarea name="note" t-att-value="note"/>
            <select name="choice" t-att-value="choice">
                <option value="a">A</option>
                <option value="b">B</option>
            </select>
        </form>`,
    );
    const html = renderToString("test.render.template.form_state", {
        name: "Old phone",
        on: true,
        off: false,
        note: "a note",
        choice: "b",
    });
    const form = document.createElement("div");
    form.innerHTML = html;
    expect(form.querySelector("[name=name]")).toHaveValue("Old phone");
    expect(form.querySelector("[name=on]")).toBeChecked();
    expect(form.querySelector("[name=off]")).not.toBeChecked();
    expect(form.querySelector("[name=note]")).toHaveValue("a note");
    expect(form.querySelector("[name=choice]")).toHaveValue("b");
});

test("renderToString adds nothing to form state the markup already reproduces", () => {
    /** @type {any} */ (renderToString.app).addTemplate(
        "test.render.template.pristine_form",
        `<div><input type="range"/><input value="x"/><select><option>A</option><option>B</option></select></div>`,
    );
    expect(renderToString("test.render.template.pristine_form")).toBe(
        `<div><input type="range"><input value="x"><select><option>A</option><option>B</option></select></div>`,
    );
});
