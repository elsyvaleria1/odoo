import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@website/js/tours/tour_utils";

registry.category("web_tour.tours").add("courses_partial_navigation", {
    steps: () => [
        {
            content: "both courses are listed",
            trigger: ".o_wslides_home_main:contains(PN Seeds):contains(PN Grafting)",
            run() {
                window.coursesPartialNavigationMarker = true;
            },
        },
        {
            content: "filter by the tag of a course's badge",
            trigger: ".o_wslides_home_main .post_link:contains(PN Beginner)",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only the tagged course is left, in place, under a filtered URL",
            trigger:
                ".o_wslides_home_main:contains(PN Seeds):not(:contains(PN Grafting))",
            run() {
                if (!window.coursesPartialNavigationMarker) {
                    throw new Error("the courses page was reloaded");
                }
                if (!window.location.pathname.startsWith("/slides/tag/")) {
                    throw new Error("the filtered URL was not pushed");
                }
            },
        },
    ],
});
