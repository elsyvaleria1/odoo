// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

/**
 * Turns the links and GET forms of a page region into in-place navigation:
 * the target URL is fetched as a whole page, the region carrying the same
 * `data-fragment` key is morphed in from it, and the URL goes into the
 * history. Only links and forms inside the scopes listed by
 * `data-partial-navigation` (a CSS selector) are taken; anything else, and
 * any answer without the region, navigates as usual. An interaction that
 * builds its URL itself dispatches a cancelable, bubbling `o-navigate` event
 * with `detail.url`, and navigates on its own when nobody took it.
 */
export class PartialNavigation extends Interaction {
    static selector = "[data-fragment][data-partial-navigation]";
    dynamicContent = {
        _root: {
            "t-on-click": this.onClick,
            "t-on-submit": this.onSubmit,
            "t-on-o-navigate": this.onNavigateRequest,
        },
        _window: { "t-on-popstate": this.onPopState },
    };

    setup() {
        this.key = this.el.dataset.fragment;
        this.scopes = this.el.dataset.partialNavigation;
        if (!browser.history.state?.partialNavigation) {
            browser.history.replaceState(
                { ...browser.history.state, partialNavigation: this.key },
                "",
            );
        }
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        const target = /** @type {Element} */ (ev.target);
        const link = /** @type {HTMLAnchorElement | null} */ (
            target.closest("a[href]")
        );
        if (
            !link ||
            ev.defaultPrevented ||
            ev.button !== 0 ||
            ev.metaKey ||
            ev.ctrlKey ||
            ev.shiftKey ||
            ev.altKey ||
            (link.target && link.target !== "_self") ||
            link.hasAttribute("download") ||
            !this._isInScope(link)
        ) {
            return;
        }
        const url = new URL(link.getAttribute("href"), browser.location.href);
        if (url.origin !== browser.location.origin) {
            return;
        }
        ev.preventDefault();
        this.navigate(url.href, { push: true });
    }

    /** @param {SubmitEvent} ev */
    onSubmit(ev) {
        const form = /** @type {HTMLFormElement} */ (ev.target);
        if (
            ev.defaultPrevented ||
            form.method.toLowerCase() !== "get" ||
            !this._isInScope(form)
        ) {
            return;
        }
        const url = new URL(form.getAttribute("action") || "", browser.location.href);
        if (url.origin !== browser.location.origin) {
            return;
        }
        const data = new FormData(form);
        if (ev.submitter?.getAttribute("name")) {
            data.append(
                ev.submitter.getAttribute("name"),
                /** @type {HTMLButtonElement} */ (ev.submitter).value,
            );
        }
        url.search = new URLSearchParams(
            /** @type {any} */ ([...data.entries()]),
        ).toString();
        ev.preventDefault();
        this.navigate(url.href, { push: true });
    }

    /** @param {CustomEvent<{ url: string }>} ev */
    onNavigateRequest(ev) {
        const url = new URL(ev.detail.url, browser.location.href);
        if (
            url.origin !== browser.location.origin ||
            !this._isInScope(/** @type {Element} */ (ev.target))
        ) {
            return;
        }
        ev.preventDefault();
        this.navigate(url.href, { push: true });
    }

    /** @param {PopStateEvent} ev */
    onPopState(ev) {
        if (ev.state?.partialNavigation === this.key) {
            this.navigate(browser.location.href, { push: false });
        }
    }

    /**
     * @param {string} url
     * @param {{ push: boolean }} options
     */
    async navigate(url, { push }) {
        const response = await this.waitFor(
            browser.fetch(url, { credentials: "same-origin" }),
        );
        const html = response.ok ? await this.waitFor(response.text()) : "";
        const page = new DOMParser().parseFromString(html, "text/html");
        const region = page.querySelector(`[data-fragment="${CSS.escape(this.key)}"]`);
        if (!region) {
            browser.location.assign(url);
            return;
        }
        if (push) {
            browser.history.pushState(
                { partialNavigation: this.key },
                "",
                response.url,
            );
        }
        const title = page.querySelector("title")?.textContent;
        if (title) {
            document.title = title;
        }
        // the region may be display: contents, which has no box of its own
        const anchor = () => this.el.firstElementChild || this.el;
        const scrolledPast = anchor().getBoundingClientRect().top < 0;
        const el = this.el;
        this.swapFragments({
            fragments: [{ key: this.key, html: region.outerHTML, swap: "morph" }],
            events: [],
            redirect: null,
            data: {},
        });
        if (scrolledPast) {
            (el.firstElementChild || el).scrollIntoView({ block: "start" });
        }
    }

    /** @param {Element} el */
    _isInScope(el) {
        const scope = el.closest(this.scopes);
        return !!scope && this.el.contains(scope);
    }
}

registry
    .category("public.interactions")
    .add("web.partial_navigation", PartialNavigation);
