/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import {
    MODULE_STATUS,
    NewContentSystrayItem,
} from "@website/client_actions/website_preview/new_content_systray_item";

patch(NewContentSystrayItem.prototype, {
    setup() {
        super.setup();

        const newEventElement = this.state.newContentElements.find(
            (element) => element.moduleXmlId === "base.module_website_event",
        );
        newEventElement.createNewContent = () =>
            this.onAddContent("website_event.event_event_action_add", true);
        newEventElement.status = MODULE_STATUS.INSTALLED;
        newEventElement.model = "event.event";
    },
});
