// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Modal, Offcanvas } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";
import {
    PARTIAL_NAVIGATION_HEADER,
    swapHead,
    swapRegions,
} from "@web/public/page_swap";

/** @typedef {{ url: string, html: string }} FetchedPage */

const PRELOAD_DELAY = 65;
const PRELOAD_TTL = 10000;

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

export class PartialNavigation extends Interaction {
    static selector = "[data-fragment][data-partial-navigation]";
    dynamicContent = {
        _root: {
            "t-on-click": this.onClick,
            "t-on-submit": this.onSubmit,
            "t-on-o-navigate": this.onNavigateRequest,
            "t-on-pointerover.noUpdate": this.onPointerOver,
            "t-on-pointerout.noUpdate": this.onPointerOut,
            "t-on-focusin.noUpdate": this.onFocusIn,
        },
        _window: { "t-on-popstate": this.onPopState },
    };

    setup() {
        this.key = this.el.dataset.fragment;
        /** @type {Map<string, { page: Promise<FetchedPage>, at: number }>} */
        this.preloads = new Map();
        /** @type {Promise<FetchedPage> | null} */
        this.preloading = null;
        this.preloadTimer = 0;
        this.scopes = window.frameElement ? null : this.el.dataset.partialNavigation;
        if (this.scopes && !browser.history.state?.partialNavigation) {
            browser.history.replaceState(
                { ...browser.history.state, partialNavigation: this.key },
                "",
            );
        }
    }

    start() {
        this.addListener(this.el, "touchstart", (ev) => this.onTouchStart(ev), {
            passive: true,
        });
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
            ev.altKey
        ) {
            return;
        }
        const url = this._linkTarget(link);
        if (url) {
            ev.preventDefault();
            this.navigate(url, { push: true });
        }
    }

    /** @param {PointerEvent} ev */
    onPointerOver(ev) {
        const link = this._closestLink(ev.target);
        if (ev.pointerType === "mouse" && link) {
            this.schedulePreload(link);
        }
    }

    /** @param {PointerEvent} ev */
    onPointerOut(ev) {
        const link = this._closestLink(ev.target);
        if (link && !link.contains(/** @type {Node | null} */ (ev.relatedTarget))) {
            clearTimeout(this.preloadTimer);
        }
    }

    /** @param {FocusEvent} ev */
    onFocusIn(ev) {
        const link = this._closestLink(ev.target);
        if (link) {
            this.schedulePreload(link);
        }
    }

    /** @param {TouchEvent} ev */
    onTouchStart(ev) {
        const link = this._closestLink(ev.target);
        if (link) {
            this.preload(link);
        }
    }

    /** @param {HTMLAnchorElement} link */
    schedulePreload(link) {
        clearTimeout(this.preloadTimer);
        this.preloadTimer = this.waitForTimeout(
            () => this.preload(link),
            PRELOAD_DELAY,
        );
    }

    /** @param {HTMLAnchorElement} link */
    preload(link) {
        const url = this._linkTarget(link);
        if (
            !url ||
            this.preloading ||
            this.el.hasAttribute("aria-busy") ||
            /** @type {{ connection?: { saveData?: boolean } }} */ (browser.navigator)
                .connection?.saveData ||
            this._freshPreload(url)
        ) {
            return;
        }
        const page = this.fetchPage(url);
        this.preloads.set(url, { page, at: Date.now() });
        this.preloading = page;
        page.then(
            () => {
                this.preloading = null;
            },
            () => {
                this.preloading = null;
                this.preloads.delete(url);
            },
        );
    }

    /**
     * @param {string} url
     * @returns {Promise<FetchedPage> | null}
     */
    _freshPreload(url) {
        const preload = this.preloads.get(url);
        if (preload && Date.now() - preload.at < PRELOAD_TTL) {
            return preload.page;
        }
        this.preloads.delete(url);
        return null;
    }

    /**
     * The page at `url`, asked without its header and footer.
     *
     * @param {string} url
     * @returns {Promise<FetchedPage>}
     */
    async fetchPage(url) {
        const response = await browser.fetch(url, {
            credentials: "same-origin",
            headers: { [PARTIAL_NAVIGATION_HEADER]: this.key },
        });
        return {
            url: response.url,
            html: response.ok ? await response.text() : "",
        };
    }

    /** @param {SubmitEvent} ev */
    onSubmit(ev) {
        const form = /** @type {HTMLFormElement} */ (ev.target);
        if (
            ev.defaultPrevented ||
            (form.getAttribute("method") || "get").toLowerCase() !== "get" ||
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
        for (const el of this.el.querySelectorAll(".offcanvas.show")) {
            Offcanvas.getInstance(el)?.hide();
        }
        for (const el of this.el.querySelectorAll(".modal.show")) {
            Modal.getInstance(el)?.hide();
        }
        clearTimeout(this.preloadTimer);
        this.el.setAttribute("aria-busy", "true");
        const preloaded = this._freshPreload(url);
        this.preloads.delete(url);
        let fetched;
        try {
            fetched = await this.waitFor(preloaded || this.fetchPage(url));
        } catch {
            browser.location.assign(url);
            return;
        }
        const page = new DOMParser().parseFromString(fetched.html, "text/html");
        if (!page.querySelector(`[data-fragment="${CSS.escape(this.key)}"]`)) {
            browser.location.assign(url);
            return;
        }
        const anchor = () => this.el.firstElementChild || this.el;
        const scrolledPast = anchor().getBoundingClientRect().top < 0;
        const el = this.el;
        swapHead(page);
        if (push) {
            browser.history.pushState({ partialNavigation: this.key }, "", fetched.url);
        }
        swapRegions(page, [el], this.services["public.interactions"]);
        if (scrolledPast) {
            (el.firstElementChild || el).scrollIntoView({ block: "start" });
        }
        window.dispatchEvent(
            new CustomEvent("o-partial-navigation", {
                detail: { key: this.key, url: fetched.url, page },
            }),
        );
    }

    /**
     * @param {EventTarget | null} target
     * @returns {HTMLAnchorElement | null}
     */
    _closestLink(target) {
        return target instanceof Element ? target.closest("a[href]") : null;
    }

    /**
     * The URL a link in scope navigates to in place; null for a link the
     * browser keeps: out of scope, another window, a download, another
     * origin, an anchor in this page.
     *
     * @param {HTMLAnchorElement} link
     * @returns {string | null}
     */
    _linkTarget(link) {
        if (
            (link.target && link.target !== "_self") ||
            link.hasAttribute("download") ||
            !this._isInScope(link)
        ) {
            return null;
        }
        const href = link.getAttribute("href");
        const url = new URL(href, browser.location.href);
        const current = new URL(browser.location.href);
        if (
            url.origin !== current.origin ||
            (href.includes("#") &&
                url.pathname === current.pathname &&
                url.search === current.search)
        ) {
            return null;
        }
        return url.href;
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
