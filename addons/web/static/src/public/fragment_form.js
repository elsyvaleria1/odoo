// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";
import { PARTIAL_NAVIGATION_HEADER, swapPage } from "@web/public/page_swap";
import { ConfirmationDialog } from "@web/ui/dialog";

// web/controllers/utils.py's FRAGMENTS_HEADER: the route may answer with the
// fragments to swap instead of redirecting, and a refusal comes as JSON
const FRAGMENTS_HEADER = "X-Odoo-Fragments";

/**
 * A post form that works without JavaScript, its route redirecting to the
 * page to show next (post/redirect/get), and updates the page in place with
 * it (htmx's boosted forms). The form's data is posted with
 * `X-Odoo-Fragments`; the answer is either
 * - fragments, from a route answering with `fragments_or_redirect`: swapped;
 * - the page the route redirected to, asked without header and footer: on
 *   the path shown, the form's regions are swapped from it, like a
 *   navigation in place, and its URL replaces the one shown; any other page
 *   is loaded in full.
 *
 * The regions are the elements keyed by `data-fragment-form` (a comma list),
 * or the closest element with a `data-fragment` key. `data-confirm` asks
 * before posting. A field marked `data-submit-on-change` submits the form
 * when it changes; without JavaScript, a submit button does. While the post
 * runs the form is `aria-busy` and further submits are dropped. A refusal
 * (a UserError, answered as JSON) shows as a notification; any other failure
 * submits the form natively.
 */
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
        if (ev.defaultPrevented || form.method !== "post") {
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
            await this.post(body);
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

    /** @param {FormData} body */
    async post(body) {
        const form = /** @type {HTMLFormElement} */ (this.el);
        const regions = this.regions();
        const response = await this.waitFor(
            browser.fetch(form.action, {
                method: "POST",
                body,
                credentials: "same-origin",
                headers: {
                    [FRAGMENTS_HEADER]: "1",
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
        if (next.href !== shown.href) {
            // what a post/redirect/get leaves in the address bar
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
