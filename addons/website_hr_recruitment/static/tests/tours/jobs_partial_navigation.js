import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@website/js/tours/tour_utils";

registry.category("web_tour.tours").add("jobs_partial_navigation", {
    steps: () => [
        {
            content: "both jobs are listed",
            trigger: "#jobs_grid:contains(PN Gardener):contains(PN Welder)",
            run() {
                window.jobsPartialNavigationMarker = true;
            },
        },
        {
            content: "type a search",
            trigger: ".o_jobs_topbar_search_bar input.oe_search_box",
            run: "edit PN Gardener",
        },
        {
            content: "search",
            trigger: ".o_jobs_topbar_search_bar .oe_search_button",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only the matching job is left, in place, under a searched URL",
            trigger: "#jobs_grid:contains(PN Gardener):not(:contains(PN Welder))",
            run() {
                if (!window.jobsPartialNavigationMarker) {
                    throw new Error("the jobs page was reloaded");
                }
                if (!window.location.search.includes("search=")) {
                    throw new Error("the searched URL was not pushed");
                }
            },
        },
    ],
});
