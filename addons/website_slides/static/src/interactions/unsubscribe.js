/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import { parseSlideBoolean } from "@website_slides/js/public/slides_course_utils";

import { SlideUnsubscribeDialog } from "../js/public/components/slide_unsubscribe_dialog/slide_unsubscribe_dialog.js";

export class Unsubscribe extends Interaction {
    static selector = ".o_wslides_js_channel_unsubscribe";
    dynamicContent = {
        _root: {
            "t-on-click.prevent": this.openDialog,
        },
    };

    openDialog() {
        const { channelId, enroll, isFollower, visibility } = this.el.dataset;
        this.services.dialog.add(SlideUnsubscribeDialog, {
            channelId: Number(channelId),
            enroll,
            isFollower: parseSlideBoolean(isFollower),
            visibility,
        });
    }
}

registry.category("public.interactions").add("website_slides.unsubscribe", Unsubscribe);
