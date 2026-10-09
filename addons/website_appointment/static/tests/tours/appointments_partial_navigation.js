import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@website/js/tours/tour_utils";

registry.category("web_tour.tours").add("appointments_partial_navigation", {
    steps: () => [
        {
            content: "both appointment types are listed",
            trigger:
                "#o_appointment_index_main_col:contains(PN Yoga):contains(PN Pilates)",
            run() {
                window.appointmentsMarker = true;
            },
        },
        {
            content: "type a search",
            trigger: ".o_appointment_index .o_searchbar_form input.oe_search_box",
            run: "edit PN Yoga",
        },
        {
            content: "search",
            trigger: ".o_appointment_index .o_searchbar_form .oe_search_button",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only the matching type is left, in place, under a searched URL",
            trigger:
                "#o_appointment_index_main_col:contains(PN Yoga):not(:contains(PN Pilates))",
            run() {
                if (!window.appointmentsMarker) {
                    throw new Error("the appointments page was reloaded");
                }
                if (!window.location.search.includes("search=")) {
                    throw new Error("the searched URL was not pushed");
                }
            },
        },
    ],
});
