import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("slides_quiz_edit_in_place", {
    steps: () => [
        {
            content: "Open the question editor",
            trigger: ".o_wslides_js_quiz_add:not(.d-none)",
            run: "click",
        },
        {
            trigger: ".o_wsildes_quiz_question_input input[name='question-name']",
            run: "edit Tour question?",
        },
        {
            trigger:
                ".o_wsildes_quiz_question_input .o_wslides_js_quiz_answer:eq(0) .o_wslides_js_quiz_answer_value",
            run: "edit Right",
        },
        {
            trigger:
                ".o_wsildes_quiz_question_input .o_wslides_js_quiz_answer:eq(1) .o_wslides_js_quiz_answer_value",
            run: "edit Wrong",
        },
        {
            content: "Mark the first answer correct",
            trigger:
                ".o_wsildes_quiz_question_input .o_wslides_js_quiz_answer:eq(0) .o_wslides_js_quiz_is_correct label",
            run: "click",
        },
        {
            content: "Save the new question",
            trigger:
                ".o_wsildes_quiz_question_input .o_wslides_js_quiz_validate_question",
            run: "click",
        },
        {
            content: "The new question stands where the placeholder stood, editor gone",
            trigger: ".o_wslides_js_lesson_quiz_question:contains('Tour question?')",
        },
        {
            trigger: "body:not(:has(.o_wsildes_quiz_question_input))",
        },
        {
            content: "Edit it",
            trigger:
                ".o_wslides_js_lesson_quiz_question:contains('Tour question?') .o_wslides_js_quiz_edit_question",
            run: "click",
        },
        {
            trigger: ".o_wsildes_quiz_question_input input[name='question-name']",
            run: "edit Tour question, edited?",
        },
        {
            content: "Update it",
            trigger: ".o_wsildes_quiz_question_input .o_wslides_js_quiz_update",
            run: "click",
        },
        {
            content: "The question is answered in place, shown again, editor gone",
            trigger:
                ".o_wslides_js_lesson_quiz_question:contains('Tour question, edited?'):visible",
        },
        {
            trigger: "body:not(:has(.o_wsildes_quiz_question_input))",
        },
    ],
});
