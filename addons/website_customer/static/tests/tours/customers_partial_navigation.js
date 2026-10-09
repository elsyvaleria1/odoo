import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@web_tour/js/utils/tour_utils";

registry.category("web_tour.tours").add("customers_partial_navigation", {
    steps: () => [
        {
            content: "both references are listed",
            trigger: "#wrap:contains(PN Acme):contains(PN Globex)",
            run() {
                window.customersPartialNavigationMarker = true;
            },
        },
        {
            content: "type a search",
            trigger: ".o_wcrm_search input[name=search]",
            run: "edit PN Acme",
        },
        {
            content: "search",
            trigger: ".o_wcrm_search .oe_search_button",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content:
                "only the matching reference is left, in place, under a searched URL",
            trigger: "#wrap:contains(PN Acme):not(:contains(PN Globex))",
            run() {
                if (!window.customersPartialNavigationMarker) {
                    throw new Error("the references page was reloaded");
                }
                if (!window.location.search.includes("search=")) {
                    throw new Error("the searched URL was not pushed");
                }
            },
        },
    ],
});
