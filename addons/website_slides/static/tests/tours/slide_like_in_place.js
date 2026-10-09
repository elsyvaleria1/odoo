import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("slide_like_in_place", {
    steps: () => [
        {
            content: "the lesson has no like yet",
            trigger: ".o_wslides_js_slide_like_up[aria-pressed=false]:contains(0)",
            run() {
                window.likeMarker = true;
            },
        },
        {
            content: "like it",
            trigger: ".o_wslides_js_slide_like_up",
            run: "click",
        },
        {
            content: "its count is 1, in place",
            trigger:
                "body:not(:has(form[aria-busy])) .o_wslides_js_slide_like_up[aria-pressed=true]:contains(1) .fa-solid",
            run() {
                if (!window.likeMarker) {
                    throw new Error("the lesson page was reloaded");
                }
            },
        },
    ],
});
