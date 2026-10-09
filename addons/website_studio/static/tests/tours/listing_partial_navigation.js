import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@website/js/tours/tour_utils";

registry.category("web_tour.tours").add("website_studio_listing_partial_navigation", {
    steps: () => [
        {
            content: "both records are listed",
            trigger: ".o_website_listing_layout:contains(PN Ada):contains(PN Grace)",
            run() {
                window.studioListingMarker = true;
            },
        },
        {
            content: "type a search",
            trigger: ".o_website_listing_layout .o_searchbar_form input[name=search]",
            run: "edit PN Ada",
        },
        {
            content: "search",
            trigger: ".o_website_listing_layout .o_searchbar_form .oe_search_button",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only the matching record is left, in place, under a searched URL",
            trigger:
                ".o_website_listing_layout:contains(PN Ada):not(:contains(PN Grace))",
            run() {
                if (!window.studioListingMarker) {
                    throw new Error("the listing was reloaded");
                }
                if (!window.location.search.includes("search=")) {
                    throw new Error("the searched URL was not pushed");
                }
            },
        },
    ],
});
