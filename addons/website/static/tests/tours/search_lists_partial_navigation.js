import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@web_tour/js/utils/tour_utils";

/**
 * @param {string} name
 * @param {string} list
 */
function searchInPlace(name, list) {
    return {
        steps: () => [
            {
                content: "both pages are listed",
                trigger: `${list}:contains(PN Alpha Page):contains(PN Beta Page)`,
                run() {
                    window.searchListMarker = name;
                },
            },
            {
                content: "type a search",
                trigger: "#wrap .o_searchbar_form input.oe_search_box",
                run: "edit PN Alpha",
            },
            {
                content: "search",
                trigger: "#wrap .o_searchbar_form .oe_search_button",
                run: "click",
            },
            waitForPartialNavigation(),
            {
                content:
                    "only the matching page is left, in place, under a searched URL",
                trigger: `${list}:contains(PN Alpha Page):not(:contains(PN Beta Page))`,
                run() {
                    if (window.searchListMarker !== name) {
                        throw new Error("the page was reloaded");
                    }
                    if (!window.location.search.includes("search=PN+Alpha")) {
                        throw new Error("the searched URL was not pushed");
                    }
                },
            },
        ],
    };
}

registry
    .category("web_tour.tours")
    .add("pages_list_partial_navigation", searchInPlace("pages", "#wrap table"))
    .add(
        "search_results_partial_navigation",
        searchInPlace("results", "#wrap .table-responsive"),
    );
