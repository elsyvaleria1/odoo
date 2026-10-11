/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import {
    getDocumentMaxPage,
    parseSlideBoolean,
} from "@website_slides/js/public/slides_course_utils";

import { SlideShareDialog } from "../js/public/components/slide_share_dialog/slide_share_dialog.js";

export class Share extends Interaction {
    static selector = ".o_wslides_share";
    dynamicContent = {
        _root: { "t-on-click.prevent.stop.withTarget": this.onClick },
    };

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    onClick(ev, currentTargetEl) {
        const data = currentTargetEl.dataset;
        this.services.dialog.add(SlideShareDialog, {
            category: data.category,
            documentMaxPage:
                data.category === "document" ? getDocumentMaxPage() : undefined,
            emailSharing: parseSlideBoolean(data.emailSharing),
            embedCode: data.embedCode,
            id: parseInt(data.id),
            isChannel: parseSlideBoolean(data.isChannel),
            name: data.name,
            url: data.url,
        });
    }
}

registry.category("public.interactions").add("website_slides.share", Share);
