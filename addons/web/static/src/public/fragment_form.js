// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";
import { PARTIAL_NAVIGATION_HEADER, swapPage } from "@web/public/page_swap";
import { TAB_HEADER, TAB_ID } from "@web/public/tab_id";
import { ConfirmationDialog } from "@web/ui/dialog";

const FRAGMENTS_HEADER = "X-Odoo-Fragments";

/** @param {FormData} submitted */
function showServerValue(submitted) {
    const field = /** @type {HTMLInputElement | null} */ (document.activeElement);
    if (field && "defaultValue" in field && field.name && submitted.has(field.name)) {
        field.value = field.defaultValue;
    }
}

export class FragmentForm extends Interaction {
    static selector = "form[data-fragment-form]";
    dynamicContent = {
        _root: { "t-on-submit": this.onSubmit },
        "[data-submit-on-change]": { "t-on-change": this.onFieldChange },
    };

    setup() {
        this.busy = false;
        this.native = false;
    }

    onFieldChange() {
        /** @type {HTMLFormElement} */ (this.el).requestSubmit();
    }

    /** @param {SubmitEvent} ev */
    async onSubmit(ev) {
        const form = /** @type {HTMLFormElement} */ (this.el);
        if (
            ev.defaultPrevented ||
            (form.getAttribute("method") || "").toLowerCase() !== "post"
        ) {
            return;
        }
        if (this.native) {
            this.native = false;
            return;
        }
        ev.preventDefault();
        if (this.busy) {
            return;
        }
        const submitter = /** @type {HTMLElement | null} */ (ev.submitter);
        const body = new FormData(form, submitter);
        this.busy = true;
        form.setAttribute("aria-busy", "true");
        try {
            if (form.dataset.confirm && !(await this.confirm(form.dataset.confirm))) {
                return;
            }
            const action =
                submitter?.getAttribute("formaction") || form.getAttribute("action");
            await this.post(body, new URL(action || "", browser.location.href).href);
        } catch {
            this.native = true;
            form.requestSubmit(submitter);
        } finally {
            this.busy = false;
            form.removeAttribute("aria-busy");
        }
    }

    /**
     * @param {string} question
     * @returns {Promise<boolean>}
     */
    confirm(question) {
        return this.waitFor(
            new Promise((resolve) => {
                this.services.dialog.add(
                    ConfirmationDialog,
                    {
                        body: question,
                        confirm: () => resolve(true),
                        cancel: () => resolve(false),
                    },
                    { onClose: () => resolve(false) },
                );
            }),
        );
    }

    /**
     * @param {FormData} body
     * @param {string} action
     */
    async post(body, action) {
        const regions = this.regions();
        const response = await this.waitFor(
            browser.fetch(action, {
                method: "POST",
                body,
                credentials: "same-origin",
                headers: {
                    [FRAGMENTS_HEADER]: "1",
                    [TAB_HEADER]: TAB_ID,
                    [PARTIAL_NAVIGATION_HEADER]: regions
                        .map((region) => region.dataset.fragment)
                        .join(","),
                },
            }),
        );
        if ((response.headers.get("Content-Type") || "").includes("application/json")) {
            const payload = await this.waitFor(response.json());
            if (response.ok) {
                this.swapFragments(payload);
                showServerValue(body);
                return;
            }
            if (payload.error?.message) {
                this.services.notification.add(payload.error.message, {
                    title: _t("This could not be done"),
                    type: "danger",
                });
                return;
            }
            throw new Error(`fragment form answered ${response.status}`);
        }
        if (!response.ok) {
            throw new Error(`fragment form answered ${response.status}`);
        }
        const html = await this.waitFor(response.text());
        const shown = new URL(browser.location.href);
        const next = new URL(response.url);
        const page = new DOMParser().parseFromString(html, "text/html");
        if (
            !regions.length ||
            next.pathname !== shown.pathname ||
            !swapPage(page, regions, this.services["public.interactions"])
        ) {
            browser.location.assign(response.url);
            return;
        }
        showServerValue(body);
        if (next.href !== shown.href) {
            browser.history.replaceState(browser.history.state, "", response.url);
        }
    }

    /** @returns {HTMLElement[]} */
    regions() {
        const keys = this.el.dataset.fragmentForm;
        if (!keys) {
            const region = /** @type {HTMLElement | null} */ (
                this.el.closest("[data-fragment]")
            );
            return region ? [region] : [];
        }
        return keys
            .split(/\s*,\s*/)
            .flatMap((key) => [
                .../** @type {NodeListOf<HTMLElement>} */ (
                    document.querySelectorAll(`[data-fragment="${CSS.escape(key)}"]`)
                ),
            ]);
    }
}

registry.category("public.interactions").add("web.fragment_form", FragmentForm);
