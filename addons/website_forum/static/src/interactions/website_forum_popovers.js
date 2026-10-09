/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Popover, Tooltip } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

export class WebsiteForumTooltip extends Interaction {
    static selector = ".website_forum [data-bs-toggle='tooltip']";

    setup() {
        const tooltip = Tooltip.getOrCreateInstance(this.el);
        this.registerCleanup(() => tooltip.dispose());
    }
}

export class WebsiteForumPopover extends Interaction {
    static selector = ".website_forum [data-bs-toggle='popover']";

    setup() {
        const popover = Popover.getOrCreateInstance(this.el);
        this.registerCleanup(() => popover.dispose());
    }
}

export class WebsiteForumBioPopover extends Interaction {
    static selector = ".website_forum .o_wforum_bio_popover";

    setup() {
        const popover = Popover.getOrCreateInstance(this.el, {
            trigger: "hover",
            offset: "10",
            animation: false,
            html: true,
            customClass: "o_wforum_bio_popover_container shadow-sm",
        });
        this.registerCleanup(() => popover.dispose());
    }
}

registry
    .category("public.interactions")
    .add("website_forum.tooltip", WebsiteForumTooltip)
    .add("website_forum.popover", WebsiteForumPopover)
    .add("website_forum.bio_popover", WebsiteForumBioPopover);
