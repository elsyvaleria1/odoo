import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("forum_vote_in_place", {
    steps: () => [
        {
            content: "the question has no votes",
            trigger: ".o_wforum_question .vote_count:contains(0)",
            run() {
                window.voteMarker = true;
            },
        },
        {
            content: "upvote it",
            trigger: ".o_wforum_question .vote_up",
            run: "click",
        },
        {
            content: "its count is 1, in place",
            trigger:
                "body:not(:has(form[aria-busy])) .o_wforum_question .vote_count.text-success:contains(1)",
            run() {
                if (!window.voteMarker) {
                    throw new Error("the question page was reloaded");
                }
            },
        },
    ],
});
