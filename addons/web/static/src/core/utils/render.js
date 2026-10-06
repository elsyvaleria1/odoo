// @ts-check
/** @odoo-module native */

import { App, blockDom, markup } from "@odoo/owl";
import { makeAppConfig } from "@web/env";

/**
 * @param {string} template
 * @param {object} [context]
 * @returns {Element | null}
 */
export function renderToElement(template, context = {}) {
    const el = render(template, context).firstElementChild;
    if (el?.nextElementSibling) {
        throw new Error(
            `The rendered template '${template}' contains multiple root ` +
                `nodes that will be ignored using renderToElement, you should ` +
                `consider using renderToFragment or refactoring the template.`,
        );
    }
    el?.remove();
    return el;
}

/**
 * @param {string} template
 * @param {object} [context]
 * @returns {DocumentFragment}
 */
export function renderToFragment(template, context = {}) {
    const frag = document.createDocumentFragment();
    for (const el of [...render(template, context).children]) {
        frag.appendChild(el);
    }
    return frag;
}

/**
 * @param {string} template
 * @param {Object} context
 */
export function renderToString(template, context = {}) {
    const div = render(template, context);
    reflectFormState(div);
    return div.innerHTML;
}

/**
 * Owl binds an input's value and checked, a textarea's value and a select's
 * choice as DOM properties, which innerHTML does not serialize: write each one
 * the markup would not reproduce back into its attribute.
 *
 * @param {HTMLElement} root
 */
function reflectFormState(root) {
    for (const el of root.querySelectorAll("input, textarea, select")) {
        const pristine = rebuild(el);
        if (el instanceof HTMLSelectElement && pristine instanceof HTMLSelectElement) {
            const options = [...el.options];
            if (
                options.some(
                    (option, i) => option.selected !== pristine.options[i].selected,
                )
            ) {
                for (const option of options) {
                    option.toggleAttribute("selected", option.selected);
                }
            }
        } else if (
            el instanceof HTMLTextAreaElement &&
            pristine instanceof HTMLTextAreaElement
        ) {
            if (el.value !== pristine.value) {
                el.defaultValue = el.value;
            }
        } else if (
            el instanceof HTMLInputElement &&
            pristine instanceof HTMLInputElement
        ) {
            if (el.checked !== pristine.checked) {
                el.toggleAttribute("checked", el.checked);
            }
            if (el.type !== "file" && el.value !== pristine.value) {
                el.setAttribute("value", el.value);
            }
        }
    }
}

/**
 * The element as its markup alone would create it: a clone carries the
 * property state over, so it cannot tell what the markup loses.
 *
 * @param {Element} el
 * @returns {Element}
 */
function rebuild(el) {
    const copy = document.createElement(el.tagName);
    for (const { name, value } of el.attributes) {
        copy.setAttribute(name, value);
    }
    for (const child of el.childNodes) {
        copy.append(child instanceof Element ? rebuild(child) : child.cloneNode());
    }
    return copy;
}
/** @type {import("@odoo/owl").App | undefined} */
let app;
Object.defineProperty(renderToString, "app", {
    get: () => {
        if (!app) {
            app = new App(
                makeAppConfig(undefined, { name: "renderToString", dev: false }),
            );
        }
        return app;
    },
    set: (value) => {
        app = value ?? undefined;
    },
    configurable: true,
});

/**
 * @param {string} template
 * @param {object} [context]
 * @returns {HTMLDivElement}
 */
function render(template, context = {}) {
    const app = /** @type {any} */ (renderToString).app;
    const templateFn = app.getTemplate(template);
    const bdom = templateFn(context, {});
    const div = document.createElement("div");
    blockDom.mount(bdom, div);
    return div;
}

/**
 * @param {string} template
 * @param {Object} context
 * @returns {import("@odoo/owl").Markup}
 */
export function renderToMarkup(template, context = {}) {
    return markup(renderToString(template, context));
}
