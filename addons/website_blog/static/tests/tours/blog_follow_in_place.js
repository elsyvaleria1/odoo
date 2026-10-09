import { registry } from "@web/core/registry";
import { waitForPartialNavigation } from "@web_tour/js/utils/tour_utils";

registry.category("web_tour.tours").add("blog_follow_in_place", {
    url: "/blog",
    steps: () => [
        {
            content: "open a blog from the blog tabs",
            trigger: "#wrap > nav.navbar a.nav-link:contains(aaa Blog Test)",
            run: "click",
        },
        waitForPartialNavigation(),
        {
            content: "type an invalid email in its follow widget, absent from /blog",
            trigger: "#o_wblog_sidebar .js_follow input.js_follow_email",
            run: "edit not-an-email",
        },
        {
            content: "subscribe",
            trigger: "#o_wblog_sidebar .js_follow .js_follow_btn",
            run: "click",
        },
        {
            content: "the widget answers: it has started",
            trigger: "#o_wblog_sidebar .js_follow.o_has_error",
        },
    ],
});
