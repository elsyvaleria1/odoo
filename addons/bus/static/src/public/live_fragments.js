// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { swapFragment } from "@web/public/fragments";
import { Interaction } from "@web/public/interaction";
import { PARTIAL_NAVIGATION_HEADER } from "@web/public/page_swap";
import { TAB_ID } from "@web/public/tab_id";

/**
 * Keeps a page's live regions in step with changes made elsewhere (htmx's
 * hx-ws, by invalidation): the server sends `fragment.invalidated` on a
 * channel it subscribed the visitor to, naming the keys that changed and the
 * page events to replay; this tab, unless it caused the change, replays the
 * events and re-reads its own page (asked without header and footer) to morph
 * each region marked `data-fragment-live` with one of those keys. The notice
 * carries no content: every tab renders under its own session and rights.
 * The bus starts only on a page with a `data-fragment-live` element; one
 * without a `data-fragment` key just hears the events.
 */
export class LiveFragments extends Interaction {
    static selector = "#wrapwrap";
    static selectorHas = "[data-fragment-live]";

    setup() {
        /** @param {{ keys?: string[], events?: Record<string, any>, origin?: string | null }} notice */
        this.onInvalidated = (notice) => this.refresh(notice);
    }

    start() {
        const bus = this.services.bus_service;
        bus.subscribe("fragment.invalidated", this.onInvalidated);
        this.registerCleanup(() =>
            bus.unsubscribe("fragment.invalidated", this.onInvalidated),
        );
        bus.start();
    }

    /**
     * @param {{ keys?: string[], events?: Record<string, any>, origin?: string | null }} notice
     */
    async refresh({ keys = [], events = {}, origin = null }) {
        if (origin === TAB_ID) {
            return;
        }
        for (const [name, detail] of Object.entries(events)) {
            document.dispatchEvent(new CustomEvent(name, { detail }));
        }
        const regions = keys.flatMap((key) => [
            .../** @type {NodeListOf<HTMLElement>} */ (
                document.querySelectorAll(
                    `[data-fragment="${CSS.escape(key)}"][data-fragment-live]`,
                )
            ),
        ]);
        if (!regions.length) {
            return;
        }
        const response = await this.waitFor(
            browser.fetch(browser.location.href, {
                credentials: "same-origin",
                headers: { [PARTIAL_NAVIGATION_HEADER]: keys.join(",") },
            }),
        );
        if (!response.ok) {
            return;
        }
        const html = await this.waitFor(response.text());
        const page = new DOMParser().parseFromString(html, "text/html");
        const interactions = this.services["public.interactions"];
        for (const region of regions) {
            const next = page.querySelector(
                `[data-fragment="${CSS.escape(region.dataset.fragment)}"]`,
            );
            if (next && region.isConnected) {
                swapFragment(region, next.outerHTML, "morph", interactions);
            }
        }
    }
}

registry.category("public.interactions").add("bus.live_fragments", LiveFragments);
