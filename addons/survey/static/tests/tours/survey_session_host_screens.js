import { registry } from "@web/core/registry";

const next = (content) => ({
    content,
    trigger: ".o_survey_session_navigation_next:not(.d-none)",
    run: "click",
});

registry.category("web_tour.tours").add("survey_session_host_screens", {
    steps: () => [
        next("Start the session"),
        {
            content: "The first question is the server's screen, faded in",
            trigger:
                ".o_survey_session_manage[data-is-rpc-call] h1:contains('Scored question')",
        },
        next("Show the attendees' inputs"),
        next("Show the results"),
        next("Show the leaderboard"),
        {
            content: "The leaderboard is the server's region",
            trigger:
                ".o_survey_session_leaderboard_container[data-fragment] .o_survey_session_leaderboard_item:contains(Ana)",
        },
        next("Go to the last question"),
        {
            trigger:
                ".o_survey_session_manage[data-is-rpc-call] h1:contains('Last question')",
        },
        {
            content: "Go back",
            trigger: ".o_survey_session_navigation_previous:not(.d-none)",
            run: "click",
        },
        {
            content:
                "The first question comes back, rendered as going back, on its leaderboard",
            trigger:
                ".o_survey_session_manage[data-going-back] .o_survey_session_leaderboard_item:contains(Ana)",
        },
    ],
});
