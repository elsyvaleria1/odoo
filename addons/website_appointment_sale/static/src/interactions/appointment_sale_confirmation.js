/** @odoo-module native */
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { Interaction } from "@web/public/interaction";

export class AppointmentSaleConfirmation extends Interaction {
    static selector = ".o_wappointment_sale_confirmation_card";

    setup() {
        if (user.userId) {
            return;
        }
        const eventAccessToken = this.el.dataset.eventAccessToken;
        const allAppointmentsToken =
            JSON.parse(
                localStorage.getItem("appointment.upcoming_events_access_token"),
            ) || [];
        if (eventAccessToken && !allAppointmentsToken.includes(eventAccessToken)) {
            allAppointmentsToken.push(eventAccessToken);
            localStorage.setItem(
                "appointment.upcoming_events_access_token",
                JSON.stringify(allAppointmentsToken),
            );
        }
    }
}

registry
    .category("public.interactions")
    .add(
        "website_appointment_sale.appointment_sale_confirmation",
        AppointmentSaleConfirmation,
    );
