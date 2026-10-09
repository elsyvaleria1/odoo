import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@website/js/tours/tour_utils";

registry.category("web_tour.tours").add("partners_partial_navigation", {
    steps: () => [
        {
            content: "both resellers are listed",
            trigger: "#wrap:contains(PN Gold Reseller):contains(PN Silver Reseller)",
            run() {
                window.partnersPartialNavigationMarker = true;
            },
        },
        {
            content: "open the grade filter",
            trigger: ".o_wcrm_filters_top .dropdown-toggle[title='Filter by category']",
            run: "click",
        },
        {
            content: "keep the gold resellers",
            trigger: ".o_wcrm_filters_top .dropdown-item:contains(PN Gold)",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only the gold reseller is left, in place, under a filtered URL",
            trigger:
                "#wrap:contains(PN Gold Reseller):not(:contains(PN Silver Reseller))",
            run() {
                if (!window.partnersPartialNavigationMarker) {
                    throw new Error("the resellers page was reloaded");
                }
                if (!window.location.pathname.includes("/grade/")) {
                    throw new Error("the filtered URL was not pushed");
                }
            },
        },
    ],
});
