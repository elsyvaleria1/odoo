import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("slide_lesson_quiz_member", {
    steps: () => [
        {
            content: "an attendee is offered to check their answers, not to join",
            trigger: ".o_wslides_lesson_main .o_wslides_js_lesson_quiz_submit",
        },
        {
            content: "and no join invitation is shown",
            trigger:
                ".o_wslides_lesson_main:not(:has(.o_wslides_quiz_join_course_message))",
        },
    ],
});
