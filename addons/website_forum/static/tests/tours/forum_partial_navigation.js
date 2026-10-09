import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@website/js/tours/tour_utils";

registry.category("web_tour.tours").add("forum_partial_navigation", {
    steps: () => [
        {
            content: "both questions are listed",
            trigger: ".o_wforum_table:contains(PN Answered):contains(PN Open)",
            run() {
                window.forumPartialNavigationMarker = true;
            },
        },
        {
            content: "open the filters",
            trigger: "#o_wforum_nav .dropdown-toggle",
            run: "click",
        },
        {
            content: "keep the unanswered questions",
            trigger: "#o_wforum_nav .dropdown-menu .dropdown-item:contains(Unanswered)",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only the open question is left, in place, its date rendered",
            trigger:
                ".o_wforum_table:contains(PN Open):not(:contains(PN Answered)) .o_wforum_relative_datetime:not(:empty)",
            run() {
                if (!window.forumPartialNavigationMarker) {
                    throw new Error("the forum page was reloaded");
                }
                if (!window.location.search.includes("filters=unanswered")) {
                    throw new Error("the filtered URL was not pushed");
                }
            },
        },
    ],
});
