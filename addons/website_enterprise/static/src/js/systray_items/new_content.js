/** @odoo-module native */
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import {
    MODULE_STATUS,
    NewContentSystrayItem,
} from "@website/client_actions/website_preview/new_content_systray_item";

patch(NewContentSystrayItem.prototype, {
    setup() {
        super.setup();

        this.state.newContentElements.push({
            moduleName: "website_appointment",
            moduleXmlId: "base.module_website_appointment",
            status: MODULE_STATUS.NOT_INSTALLED,
            icon: "/calendar/booking/static/description/icon.png",
            title: _t("Appointment Form"),
            description: _t("Let visitors book meetings online"),
        });
    },
});
