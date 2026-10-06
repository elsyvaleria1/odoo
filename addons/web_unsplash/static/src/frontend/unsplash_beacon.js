/** @odoo-module native */
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class UnsplashBeacon extends Interaction {
    static selector = "#wrapwrap";

    async willStart() {
        const unsplashImageEls = this.el.querySelectorAll("img[src*='/unsplash/']");
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
