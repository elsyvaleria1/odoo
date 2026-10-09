/** @odoo-module native */
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class UnsplashBeacon extends Interaction {
    static selector = "#wrapwrap";
    dynamicContent = {
        _root: {
            "t-on-o-fragment-swapped.noUpdate": ({ target }) =>
                this.reportViews(target),
        },
    };

    async willStart() {
        await this.reportViews(this.el);
    }

    /** @param {HTMLElement} el */
    async reportViews(el) {
        const unsplashImageEls = el.querySelectorAll("img[src*='/unsplash/']");
        const unsplashImageIds = [];
        for (const unsplashImageEl of unsplashImageEls) {
            unsplashImageIds.push(
                unsplashImageEl.src.split("/unsplash/")[1].split("/")[0],
            );
        }

        if (unsplashImageIds.length) {
            const appID = await this.waitFor(rpc("/web_unsplash/get_app_id"));

            if (appID) {
                const fetchURL = new URL("https://views.unsplash.com/v");
                fetchURL.search = new URLSearchParams({
                    photo_id: unsplashImageIds.join(","),
                    app_id: appID,
                });
                fetch(fetchURL);
            }
        }
    }
}

registry
    .category("public.interactions")
    .add("web_unsplash.unsplash_beacon", UnsplashBeacon);
