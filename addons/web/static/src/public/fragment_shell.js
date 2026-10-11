// @ts-check
/** @odoo-module native */

import { morph } from "@web/core/utils/dom/morph";

/**
 * @typedef {{ key: string, html: string, swap: "morph" | "inner" | "outer" }} ShellFragment
 * @typedef {{ fragments: ShellFragment[], events: { name: string, detail: any }[], redirect: string | null, data: Record<string, any> }} ShellResponse
 * @typedef {{
 *   headers?: () => Record<string, string>,
 *   onSwap?: (page: Document | null) => void,
 *   onRefused?: (message: string) => void,
 * }} ShellOptions
 */

const FRAGMENTS_HEADER = "X-Odoo-Fragments";
const PARTIAL_NAVIGATION_HEADER = "X-Odoo-Partial-Navigation";

/**
 * @param {string} html
 * @returns {Document}
 */
function parsePage(html) {
    return new DOMParser().parseFromString(html, "text/html");
}

export class FragmentShell {
    /**
     * @param {HTMLElement} root
     * @param {ShellOptions} [options]
     */
    constructor(root, options = {}) {
        this.root = root;
        this.headers = options.headers || (() => ({}));
        this.onSwap = options.onSwap || (() => {});
        this.onRefused = options.onRefused || ((message) => window.alert(message));
        this.busy = false;
        this.onClick = this.onClick.bind(this);
        this.onSubmit = this.onSubmit.bind(this);
        this.onPopState = this.onPopState.bind(this);
    }

    start() {
        this.root.addEventListener("click", this.onClick);
        this.root.addEventListener("submit", this.onSubmit);
        window.addEventListener("popstate", this.onPopState);
    }

    stop() {
        this.root.removeEventListener("click", this.onClick);
        this.root.removeEventListener("submit", this.onSubmit);
        window.removeEventListener("popstate", this.onPopState);
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        const link = /** @type {HTMLAnchorElement | null} */ (
            ev.target instanceof Element ? ev.target.closest("a[href]") : null
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
            link.closest("[data-no-fragment]")
        ) {
            return;
        }
        const url = new URL(link.getAttribute("href") || "", window.location.href);
        const current = new URL(window.location.href);
        if (
            url.origin !== current.origin ||
            (link.getAttribute("href")?.includes("#") &&
                url.pathname === current.pathname &&
                url.search === current.search)
        ) {
            return;
        }
        ev.preventDefault();
        this.visit(url.href);
    }

    /** @param {SubmitEvent} ev */
    onSubmit(ev) {
        const form = /** @type {HTMLFormElement} */ (ev.target);
        if (ev.defaultPrevented || form.closest("[data-no-fragment]")) {
            return;
        }
        ev.preventDefault();
        const submitter = /** @type {HTMLElement | null} */ (ev.submitter);
        const action =
            submitter?.getAttribute("formaction") || form.getAttribute("action") || "";
        const url = new URL(action, window.location.href);
        const body = new FormData(form, submitter);
        if ((form.getAttribute("method") || "get").toLowerCase() === "get") {
            url.search = new URLSearchParams(/** @type {any} */ ([...body])).toString();
            this.visit(url.href);
        } else {
            this.post(url.href, body);
        }
    }

    /** @param {PopStateEvent} ev */
    onPopState(ev) {
        if (ev.state?.fragmentShell) {
            this.visit(window.location.href, { push: false });
        }
    }

    /**
     * @param {string} url
     * @param {{ push?: boolean }} [options]
     */
    async visit(url, { push = true } = {}) {
        const response = await this.request(url, {});
        if (!response) {
            return;
        }
        const page = parsePage(await response.text());
        if (!this.hasRegionOf(page)) {
            this.leave(response.url);
            return;
        }
        if (push) {
            window.history.pushState({ fragmentShell: true }, "", response.url);
        }
        this.swapPage(page);
    }

    /** @param {string} url */
    leave(url) {
        window.location.assign(url);
    }

    /** @param {Document} page */
    hasRegionOf(page) {
        return [
            .../** @type {NodeListOf<HTMLElement>} */ (
                this.root.querySelectorAll("[data-fragment]")
            ),
        ].some((region) =>
            page.querySelector(
                `[data-fragment="${CSS.escape(region.dataset.fragment || "")}"]`,
            ),
        );
    }

    /**
     * @param {string} url
     * @param {FormData} body
     */
    async post(url, body) {
        if (this.busy) {
            return;
        }
        this.busy = true;
        this.root.setAttribute("aria-busy", "true");
        try {
            const response = await this.request(url, {
                method: "POST",
                body,
                headers: { [FRAGMENTS_HEADER]: "1" },
            });
            if (!response) {
                return;
            }
            if ((response.headers.get("Content-Type") || "").includes("json")) {
                this.applyFragments(await response.json());
                return;
            }
            const page = parsePage(await response.text());
            if (!this.hasRegionOf(page)) {
                this.leave(response.url);
                return;
            }
            if (new URL(response.url).pathname !== window.location.pathname) {
                window.history.pushState({ fragmentShell: true }, "", response.url);
            } else {
                window.history.replaceState({ fragmentShell: true }, "", response.url);
            }
            this.swapPage(page);
        } finally {
            this.busy = false;
            this.root.removeAttribute("aria-busy");
        }
    }

    /**
     * @param {string} url
     * @param {RequestInit & { headers?: Record<string, string> }} init
     * @returns {Promise<Response | null>} null when refused or failed
     */
    async request(url, init) {
        let response;
        try {
            response = await window.fetch(url, {
                credentials: "same-origin",
                ...init,
                headers: {
                    [PARTIAL_NAVIGATION_HEADER]: "1",
                    ...this.headers(),
                    ...init.headers,
                },
            });
        } catch {
            this.onRefused("");
            return null;
        }
        if (response.ok) {
            return response;
        }
        let message = "";
        if ((response.headers.get("Content-Type") || "").includes("json")) {
            message = (await response.json()).error?.message || "";
        }
        this.onRefused(message);
        return null;
    }

    /**
     * Morphs each region of the shell from its counterpart in `page`, and the
     * title and language.
     *
     * @param {Document} page
     */
    swapPage(page) {
        const title = page.querySelector("title")?.textContent;
        if (title) {
            document.title = title;
        }
        const lang = page.documentElement.getAttribute("lang");
        if (lang) {
            document.documentElement.setAttribute("lang", lang);
        }
        for (const region of /** @type {NodeListOf<HTMLElement>} */ (
            this.root.querySelectorAll("[data-fragment]")
        )) {
            const key = region.dataset.fragment;
            if (region.parentElement?.closest("[data-fragment]")) {
                continue;
            }
            const next = page.querySelector(`[data-fragment="${CSS.escape(key)}"]`);
            if (next) {
                morph(region, next);
            }
        }
        this.onSwap(page);
    }

    /** @param {ShellResponse} response */
    applyFragments(response) {
        for (const { key, html, swap } of response.fragments) {
            const next = parsePage(`<body>${html}</body>`).body.firstElementChild;
            if (!next) {
                continue;
            }
            for (const target of /** @type {NodeListOf<HTMLElement>} */ (
                this.root.querySelectorAll(`[data-fragment="${CSS.escape(key)}"]`)
            )) {
                if (swap === "outer") {
                    target.replaceWith(next.cloneNode(true));
                } else if (swap === "inner") {
                    const children = document.createDocumentFragment();
                    children.append(...next.cloneNode(true).childNodes);
                    morph(target, children, { inner: true });
                } else {
                    morph(target, /** @type {Element} */ (next.cloneNode(true)));
                }
            }
        }
        this.onSwap(null);
        for (const { name, detail } of response.events) {
            document.dispatchEvent(new CustomEvent(name, { detail }));
        }
        if (response.redirect) {
            this.visit(new URL(response.redirect, window.location.href).href);
        }
    }
}
