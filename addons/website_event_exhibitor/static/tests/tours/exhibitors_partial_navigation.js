import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@web_tour/js/utils/tour_utils";

registry.category("web_tour.tours").add("exhibitors_partial_navigation", {
    steps: () => [
        {
            content: "both exhibitors are listed",
            trigger: ".o_wesponsor_index:contains(PN Brussels):contains(PN Paris)",
            run() {
                window.exhibitorsPartialNavigationMarker = true;
            },
        },
        {
            content: "open the country filter",
            trigger:
                ".o_wesponsor_topbar_filters .dropdown-toggle:contains(By Country)",
            run: "click",
        },
        {
            content: "keep the French exhibitors",
            trigger:
                ".o_wesponsor_topbar_filters .dropdown-menu .post_link:contains(France)",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content:
                "only the French exhibitor is left, in place, under a filtered URL",
            trigger:
                ".o_wesponsor_index:contains(PN Paris):not(:contains(PN Brussels))",
            run() {
                if (!window.exhibitorsPartialNavigationMarker) {
                    throw new Error("the exhibitors page was reloaded");
                }
                if (!window.location.search.includes("countries=")) {
                    throw new Error("the filtered URL was not pushed");
                }
            },
        },
    ],
});
