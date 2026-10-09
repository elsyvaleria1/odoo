// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Modal, Offcanvas } from "@web/libs/bootstrap";
import { swapFragment } from "@web/public/fragments";
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

const OUT_OF_BAND = "[data-fragment][data-partial-navigation-oob]";

/** @typedef {{ url: string, html: string }} FetchedPage */

// a pointer resting this long on a link announces a click
const PRELOAD_DELAY = 65;
// how long a preloaded page stays good for the click it announced
const PRELOAD_TTL = 10000;

// http_routing's PARTIAL_NAVIGATION_HEADER: the server leaves out the header
// and footer, which a navigation in place keeps
const PARTIAL_NAVIGATION_HEADER = "X-Odoo-Partial-Navigation";

/**
 * The out-of-band elements of `root` outside `region`, by key, in document
 * order.
 *
 * @param {ParentNode} root
 * @param {Element} region
 * @returns {Map<string, HTMLElement[]>}
 */
function outOfBandByKey(root, region) {
    const byKey = new Map();
    for (const el of /** @type {NodeListOf<HTMLElement>} */ (
        root.querySelectorAll(OUT_OF_BAND)
    )) {
        if (!region.contains(el)) {
            const key = el.dataset.fragment;
            byKey.set(key, [...(byKey.get(key) || []), el]);
        }
    }
    return byKey;
}

/**
 * @param {Element} current
 * @param {Element} next
 * @param {string[]} names
 */
function syncAttributes(current, next, names) {
    for (const name of names) {
        const value = next.getAttribute(name);
        if (value === null) {
            current.removeAttribute(name);
        } else {
            current.setAttribute(name, value);
        }
    }
}

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
 * server rendered outside the region. Elements outside the region marked
 * `data-partial-navigation-oob` with a `data-fragment` key follow along.
 *
 * A link in scope is preloaded (htmx's preload extension) once a mouse rests
 * on it, a finger touches it or the keyboard focuses it: the click then
 * finds its page fetched or on its way. One preload at a time, none when
 * the browser asks to save data.
 */
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

    start() {
        // passive: a touch listener that may cancel would hold back scrolling
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
        clearTimeout(this.preloadTimer);
        // the swapped-in region carries no aria-busy, so the morph clears it
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
        const region = page.querySelector(`[data-fragment="${CSS.escape(this.key)}"]`);
        if (!region) {
            browser.location.assign(url);
            return;
        }
        if (push) {
            browser.history.pushState({ partialNavigation: this.key }, "", fetched.url);
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
        this.swapOutOfBand(page, region);
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
     * Elements outside the region that the server renders for the URL
     * follow the page (htmx's hx-swap-oob), found in the next page by their
     * `data-fragment` key:
     * - `data-partial-navigation-oob=""` (the breadcrumbs): each is morphed
     *   from its counterpart, paired by document order, and hidden when the
     *   next page has none. It must live in the page's content, which a page
     *   asked for in place still renders.
     * - `data-partial-navigation-oob="href"` (the language links, in the
     *   header and footer a page asked for in place leaves out): every
     *   element of the key takes the listed attributes from the first
     *   counterpart, which the server also renders, hidden, in that case.
     *
     * @param {Document} page
     * @param {Element} region the region in `page`
     */
    swapOutOfBand(page, region) {
        const interactions = this.services["public.interactions"];
        const next = outOfBandByKey(page, region);
        for (const [key, elements] of outOfBandByKey(document, this.el)) {
            const counterparts = next.get(key) || [];
            const attributes = elements[0].dataset.partialNavigationOob;
            if (attributes) {
                if (counterparts[0]) {
                    for (const el of elements) {
                        syncAttributes(
                            el,
                            counterparts[0],
                            attributes.split(/\s*,\s*/),
                        );
                    }
                }
                continue;
            }
            elements.forEach((el, index) => {
                const counterpart = counterparts[index];
                if (counterpart) {
                    swapFragment(el, counterpart.outerHTML, "morph", interactions);
                } else {
                    el.hidden = true;
                }
            });
        }
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
