import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("forum_favorite_in_place", {
    steps: () => [
        {
            content: "the question is not a favorite",
            trigger: ".o_wforum_favorite_toggle[aria-pressed=false]",
            run() {
                window.favoriteMarker = true;
            },
        },
        {
            content: "star it",
            trigger: ".o_wforum_favorite_toggle",
            run: "click",
        },
        {
            content: "it is starred, in place",
            trigger:
                "body:not(:has(form[aria-busy])) .o_wforum_favorite_toggle[aria-pressed=true] .fa-star.fa-solid",
            run() {
                if (!window.favoriteMarker) {
                    throw new Error("the question page was reloaded");
                }
            },
        },
    ],
});
