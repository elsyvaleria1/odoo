/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { EditWebsiteSystrayItem } from "@website/client_actions/website_preview/edit_website_systray_item";

import { isFullscreenSlide, lessonLocation } from "./fullscreen_slide_location.js";

patch(EditWebsiteSystrayItem.prototype, {
    getLocation() {
        const location = this.websiteService.contentWindow.location;
        if (isFullscreenSlide(location)) {
            return lessonLocation(location);
        }
        return super.getLocation(...arguments);
    },
});
