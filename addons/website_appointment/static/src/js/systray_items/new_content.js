/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import {
    MODULE_STATUS,
    NewContentSystrayItem,
} from "@website/client_actions/website_preview/new_content_systray_item";

patch(NewContentSystrayItem.prototype, {
    setup() {
        super.setup();

        const newAppointmentTypeElement = this.state.newContentElements.find(
            (element) => element.moduleXmlId === "base.module_website_appointment",
        );
        newAppointmentTypeElement.createNewContent = () =>
            this.onAddContent(
                "website_appointment.appointment_type_action_add_simplified",
            );
        newAppointmentTypeElement.status = MODULE_STATUS.INSTALLED;
        newAppointmentTypeElement.model = "appointment.type";
    },
});
