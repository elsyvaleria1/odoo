// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { swapFragment } from "@web/public/fragments";
import { Interaction } from "@web/public/interaction";
import { PARTIAL_NAVIGATION_HEADER } from "@web/public/page_swap";
import { TAB_ID } from "@web/public/tab_id";

export class LiveFragments extends Interaction {
    static selector = "#wrapwrap";
    static selectorHas = "[data-fragment-live]";

    setup() {
        /** @param {{ keys?: string[], events?: Record<string, any>, origin?: string | null }} notice */
        this.onInvalidated = (notice) => this.refresh(notice);
        this.refreshes = 0;
        /** @type {Map<string, number>} */
        this.appliedRefreshOf = new Map();
    }

    start() {
        const bus = this.services.bus_service;
        this.registerCleanup(bus.subscribe("fragment.invalidated", this.onInvalidated));
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
        const refresh = ++this.refreshes;
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
            const key = region.dataset.fragment ?? "";
            if ((this.appliedRefreshOf.get(key) ?? 0) > refresh) {
                continue;
            }
            this.appliedRefreshOf.set(key, refresh);
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
