import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("event_slot_registration", {
    steps: () => [
        {
            content: "Open the date picker",
            trigger: ".o_wevent_registration_cta:contains(Register)",
            run: "click",
        },
        {
            content: "Next waits for a date",
            trigger: ".modal.show #slot_registration_form .a-submit:disabled",
        },
        {
            content: "Pick the first date",
            trigger:
                ".modal.show #slot_registration_form label.o_wevent_slot_btn:first",
            run: "click",
        },
        {
            content: "The picked date is shown and Next is enabled",
            trigger:
                ".modal.show .o_wevent_selected_slot_title:contains(Selected Date) ~ .o_wevent_selected_slot:not(:empty)",
        },
        {
            content: "Ask for that date's tickets",
            trigger: ".modal.show #slot_registration_form .a-submit:enabled",
            run: "click",
        },
        {
            content: "The tickets of the date come as a modal",
            trigger:
                ".modal.show.o_wevent_modal_slot_ticket_registration #registration_form",
        },
        {
            content: "Register one ticket",
            trigger:
                ".modal.show.o_wevent_modal_slot_ticket_registration .a-submit:enabled:contains(Register)",
            run: "click",
        },
        {
            content: "The attendees come as a modal",
            trigger: ".modal.modal_shown.show form[id=attendee_registration]",
        },
        {
            trigger: ".modal #attendee_registration input[name*='1-name']",
            run: "edit Slot Attendee",
        },
        {
            trigger: ".modal #attendee_registration input[name*='1-email']",
            run: "edit slot.attendee@example.com",
        },
        {
            content: "Confirm the registration",
            trigger: ".modal #attendee_registration button[type=submit]:enabled",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "The registration is confirmed",
            trigger: ".o_wereg_confirmed h1:contains(Registration confirmed)",
        },
    ],
});
