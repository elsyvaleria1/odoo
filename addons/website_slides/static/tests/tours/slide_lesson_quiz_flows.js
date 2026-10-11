import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("slide_lesson_quiz_join_and_submit", {
    steps: () => [
        {
            content: "a visitor of a preview quiz picks an answer before joining",
            trigger: ".o_wslides_lesson_main .o_wslides_quiz_answer:contains(Right)",
            run: "click",
        },
        {
            content: "and joins the course, submitting the answer with it",
            trigger: ".o_wslides_lesson_main .o_wslides_js_course_join_link",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "once a member, the saved answer is re-applied and submitted",
            trigger: ".o_wslides_quiz_modal_close_btn",
            run: "click",
        },
        {
            trigger: ".o_wslides_js_lesson_quiz_validation:contains(Done!)",
        },
    ],
});

registry.category("web_tour.tours").add("slide_lesson_quiz_complete_and_reset", {
    steps: () => [
        {
            trigger: ".o_wslides_lesson_main .o_wslides_quiz_answer:contains(Right)",
            run: "click",
        },
        {
            trigger: ".o_wslides_lesson_main .o_wslides_js_lesson_quiz_submit",
            run: "click",
        },
        {
            trigger: ".o_wslides_quiz_modal_close_btn",
            run: "click",
        },
        {
            content: "the member who completed the quiz may reset their own progress",
            trigger:
                ".o_wslides_js_lesson_quiz_validation .o_wslides_js_lesson_quiz_reset",
        },
        {
            content: "Take Quiz became a POST form back to To Do, not a GET link",
            trigger:
                "form[method=post][action$='/set_uncompleted']:has(input[name=csrf_token]) button.o_wslides_undone_button",
        },
        {
            trigger: "body:not(:has(a.o_wslides_done_button))",
        },
        {
            content: "resetting brings the quiz back unanswered",
            trigger: ".o_wslides_js_lesson_quiz_reset",
            run: "click",
            expectUnloadPage: true,
        },
        {
            trigger: ".o_wslides_lesson_main .o_wslides_js_lesson_quiz_submit",
        },
        {
            trigger:
                ".o_wslides_lesson_main:not(:has(.o_wslides_js_lesson_quiz_reset))",
        },
    ],
});
