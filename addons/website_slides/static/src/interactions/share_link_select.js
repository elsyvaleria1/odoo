/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class ShareLinkSelect extends Interaction {
    static selector = ".o_wslides_js_share_link";
    dynamicContent = {
        _root: { "t-on-click": this.onClick },
    };

    onClick() {
        /** @type {HTMLInputElement} */ (this.el).select();
    }
}

registry
    .category("public.interactions")
    .add("website_slides.share_link_select", ShareLinkSelect);
