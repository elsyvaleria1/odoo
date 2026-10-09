/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import { requestNavigation } from "@web/public/partial_navigation";
import { sendRequest } from "@website/js/utils";

const log = makeLogger("website.interaction.post_link");

export class PostLink extends Interaction {
    static selector = ".post_link";
    dynamicSelectors = {
        ...this.dynamicSelectors,
        _select: () => this.el.matches("select") && this.el,
        _nonSelect: () => !this.el.matches("select") && this.el,
    };
    dynamicContent = {
        _root: {
            "t-att-class": () => ({
                o_post_link_js_loaded: true,
            }),
        },
        _nonSelect: {
            "t-on-click.prevent": this.onClickPost,
        },
        _select: {
            "t-on-change.prevent": this.onClickPost,
        },
    };

    onClickPost() {
        const data = {};
        for (const [key, value] of Object.entries(this.el.dataset)) {
            if (key.startsWith("post_")) {
                data[key.slice(5)] = value;
            }
        }
        const url = this.el.dataset.post || this.el.href || this.el.value;
        log.pipeline("PostLink onClickPost: send request", () => ({
            url,
            params: Object.keys(data),
        }));
        const post = () => sendRequest(url, data);
        if (Object.keys(data).length) {
            post();
            return;
        }
        // with nothing to post, the target renders the same page to a GET,
        // which a partial navigation region can then take in place
        requestNavigation(this.el, url, post);
    }
}

registry.category("public.interactions").add("website.post_link", PostLink);
