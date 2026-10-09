// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Modal, Offcanvas } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

// what a page says about itself in <head>, kept in step with the page shown
const HEAD_SELECTORS = [
    'link[rel="canonical"]',
    'link[rel="alternate"][hreflang]',
    'meta[name="description"]',
    'meta[name="robots"]',
    'meta[property^="og:"]',
    'meta[name^="twitter:"]',
].join(", ");

/**
 * The page metadata <html> carries (main object, view, website, lang).
 *
 * @param {Element} current
 * @param {Element} next
 */
function syncPageAttributes(current, next) {
    const isPageAttribute = (/** @type {string} */ name) =>
        name.startsWith("data-") || name === "lang" || name === "dir";
    for (const { name } of [...current.attributes]) {
        if (isPageAttribute(name) && !next.hasAttribute(name)) {
            current.removeAttribute(name);
        }
    }
    for (const { name, value } of next.attributes) {
        if (isPageAttribute(name)) {
            current.setAttribute(name, value);
        }
    }
}

/**
 * Navigates to `url` in place when `el` sits in a partial navigation scope,
 * and through `fallback` otherwise (a plain navigation by default).
 *
 * @param {Element} el
 * @param {string} url
 * @param {() => void} [fallback]
 */
export function requestNavigation(
    el,
    url,
    fallback = () => browser.location.assign(new URL(url, browser.location.href).href),
) {
    const request = new CustomEvent("o-navigate", {
        bubbles: true,
        cancelable: true,
        detail: { url },
    });
    if (el.dispatchEvent(request)) {
        fallback();
    }
}

/**
 * Turns the links and GET forms of a page region into in-place navigation:
 * the target URL is fetched as a whole page, the region carrying the same
 * `data-fragment` key is morphed in from it, and the URL goes into the
 * history. Only links and forms inside the scopes listed by
 * `data-partial-navigation` (a CSS selector) are taken, except under a
 * `data-no-partial-navigation` element (htmx's `hx-boost="false"`): an
 * autocomplete menu inside a scoped search form links to other pages.
 * Anything else, and any answer without the region, navigates as usual. An interaction that
 * builds its URL itself dispatches a cancelable, bubbling `o-navigate` event
 * with `detail.url`, and navigates on its own when nobody took it. After each
 * in-place navigation, `window` receives an `o-partial-navigation` event
 * (`detail.key`, `detail.url`, and `detail.page`, the fetched page as a
 * Document) for code that otherwise runs on page load or reads what the
 * server rendered outside the region.
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
        // a page embedded by a same-origin frame (the website builder's preview)
        // navigates as usual: the embedder follows the page through its loads
        this.scopes = window.frameElement ? null : this.el.dataset.partialNavigation;
        if (this.scopes && !browser.history.state?.partialNavigation) {
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
        if (this.scopes && ev.state?.partialNavigation === this.key) {
            this.navigate(browser.location.href, { push: false });
        }
    }

    /**
     * @param {string} url
     * @param {{ push: boolean }} options
     */
    async navigate(url, { push }) {
        // the morph would drop their `show` class but not the backdrop and
        // scroll lock Bootstrap put on the body
        for (const el of this.el.querySelectorAll(".offcanvas.show")) {
            Offcanvas.getInstance(el)?.hide();
        }
        for (const el of this.el.querySelectorAll(".modal.show")) {
            Modal.getInstance(el)?.hide();
        }
        // the swapped-in region carries no aria-busy, so the morph clears it
        this.el.setAttribute("aria-busy", "true");
        let response;
        try {
            response = await this.waitFor(
                browser.fetch(url, { credentials: "same-origin" }),
            );
        } catch {
            browser.location.assign(url);
            return;
        }
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
        for (const el of document.head.querySelectorAll(HEAD_SELECTORS)) {
            el.remove();
        }
        document.head.append(
            ...[...page.head.querySelectorAll(HEAD_SELECTORS)].map((el) =>
                document.importNode(el, true),
            ),
        );
        syncPageAttributes(document.documentElement, page.documentElement);
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
        window.dispatchEvent(
            new CustomEvent("o-partial-navigation", {
                detail: { key: this.key, url: response.url, page },
            }),
        );
    }

    /** @param {Element} el */
    _isInScope(el) {
        if (!this.scopes || el.closest("[data-no-partial-navigation]")) {
            return false;
        }
        const scope = el.closest(this.scopes);
        return !!scope && this.el.contains(scope);
    }
}

registry
    .category("public.interactions")
    .add("web.partial_navigation", PartialNavigation);
