import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@web_tour/js/utils/tour_utils";

registry.category("web_tour.tours").add("tracks_partial_navigation", {
    steps: () => [
        {
            content: "both tracks are listed",
            trigger: ".o_wesession_index:contains(PN Closing):contains(PN Opening)",
            run() {
                window.tracksPartialNavigationMarker = true;
            },
        },
        {
            content: "filter by the tag of a track's badge",
            trigger: ".o_wesession_index .post_link:contains(PN Keynote)",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "only the tagged track is left, in place, under a filtered URL",
            trigger:
                ".o_wesession_index:contains(PN Opening):not(:contains(PN Closing))",
            run() {
                if (!window.tracksPartialNavigationMarker) {
                    throw new Error("the tracks page was reloaded");
                }
                if (!window.location.search.includes("tags=")) {
                    throw new Error("the filtered URL was not pushed");
                }
            },
        },
    ],
});
