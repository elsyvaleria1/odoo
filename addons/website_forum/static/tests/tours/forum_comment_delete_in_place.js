import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("forum_comment_delete_in_place", {
    steps: () => [
        {
            content: "the comment is there",
            trigger: ".o_wforum_post_comment:contains(PN doomed comment)",
            run() {
                window.commentDeleteMarker = true;
            },
        },
        {
            content: "open the comment's menu",
            trigger: ".o_wforum_post_comment:contains(PN doomed comment) .dropdown > a",
            run: "click",
        },
        {
            content: "delete it",
            trigger:
                ".o_wforum_post_comment:contains(PN doomed comment) .comment_delete",
            run: "click",
        },
        {
            content: "confirm",
            trigger: ".modal .modal-footer .btn-primary",
            run: "click",
        },
        {
            content: "the comment is gone, in place",
            trigger:
                "body:not(:has(form[aria-busy])):not(:has(.o_wforum_post_comment:contains(PN doomed comment)))",
            run() {
                if (!window.commentDeleteMarker) {
                    throw new Error("the question page was reloaded");
                }
            },
        },
    ],
});
