/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { WebsiteBuilderClientAction } from "@website/client_actions/website_preview/website_builder_action";

import { isFullscreenSlide, lessonLocation } from "./fullscreen_slide_location.js";

patch(WebsiteBuilderClientAction.prototype, {
    async onEditPage() {
        await this.iframeLoaded;
        if (this.isNavigatingToAnotherPage) {
            await this.isNavigatingToAnotherPage;
        }
        const location = this.websiteService.contentWindow.location;
        if (isFullscreenSlide(location)) {
            const { pathname, search, hash } = lessonLocation(location);
            this.websiteService.goToWebsite({
                path: pathname + search + hash,
                edition: true,
            });
            return;
        }
        return super.onEditPage(...arguments);
    },
});
