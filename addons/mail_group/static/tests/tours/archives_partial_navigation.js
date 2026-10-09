import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@web_tour/js/utils/tour_utils";

registry.category("web_tour.tours").add("mail_group_archives_partial_navigation", {
    steps: () => [
        {
            content: "both months' threads are listed",
            trigger: "#wrap:contains(PN January):contains(PN March)",
            run() {
                window.archivesMarker = true;
            },
        },
        {
            content: "keep January's threads",
            trigger: "#group_mode a.nav-link:contains(January)",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only January's thread is left, in place",
            trigger: "#wrap:contains(PN January):not(:contains(PN March))",
            run() {
                if (!window.archivesMarker) {
                    throw new Error("the archives page was reloaded");
                }
            },
        },
        {
            content: "the breadcrumb, outside the region, followed the page",
            trigger: ".o_portal .breadcrumb a[href*='date_begin']",
        },
    ],
});
