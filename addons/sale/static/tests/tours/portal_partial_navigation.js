import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("portal_partial_navigation", {
    url: "/my/quotes",
    steps: () => [
        {
            content: "the newest quotation comes first",
            trigger: "table tbody tr:first-child a:text(PN Zulu)",
            run() {
                window.portalPartialNavigationMarker = true;
            },
        },
        {
            content: "open the sort menu",
            trigger: "#portal_searchbar_sortby",
            run: "click",
        },
        {
            content: "sort by name",
            trigger: "[aria-labelledby=portal_searchbar_sortby] a:text(Name)",
            run: "click",
        },
        {
            content: "the list is sorted in place and the URL says so",
            trigger: "table tbody tr:first-child a:text(PN Alpha)",
            run() {
                if (!window.portalPartialNavigationMarker) {
                    throw new Error("the page was reloaded");
                }
                if (!window.location.search.includes("sortby=name")) {
                    throw new Error("the sorted URL was not pushed");
                }
            },
        },
        {
            content: "go back",
            trigger: "#portal_searchbar_sortby:contains(Name)",
            run() {
                window.history.back();
            },
        },
        {
            content: "going back restores the newest-first list in place",
            trigger: "table tbody tr:first-child a:text(PN Zulu)",
            run() {
                if (!window.portalPartialNavigationMarker) {
                    throw new Error("going back reloaded the page");
                }
            },
        },
    ],
});
