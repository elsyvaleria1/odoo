import { registry } from "@web/core/registry";

let uniqueSeed = 0;

const triggerEnterEvent = (element) => {
    const ev = new window.KeyboardEvent("keydown", { bubbles: true, key: "Enter" });
    element.dispatchEvent(ev);
};

function createReplies(textareaSelector) {
    const maximumAllowedReplies = 3;
    uniqueSeed += 1;

    const tourSteps = [];

    for (let i = 0; i < maximumAllowedReplies; i++) {
        const message = `__social_twitter_test_tour_${uniqueSeed}_${i}__`;

        tourSteps.push(
            {
                trigger: ".o_social_comments_modal textarea",
                content: `Reply number ${i}`,
                run({ queryOne }) {
                    const inputComment = queryOne(textareaSelector);
                    inputComment.value = message;
                    triggerEnterEvent(inputComment);
                },
            },
            {
                trigger: `.o_social_comment_text[data-original-message*="${message}"]`,
                content: "Check if the comment has been posted",
                run: "click",
            },
        );
    }

    const message = `__social_twitter_test_tour_${uniqueSeed}_last__`;
    tourSteps.push(
        {
            trigger: ".o_social_comments_modal textarea",
            content: "Write the last comment that will fail",
            run({ queryOne }) {
                const inputComment = queryOne(textareaSelector);
                inputComment.value = message;
                triggerEnterEvent(inputComment);
            },
        },
        {
            trigger: ".o_social_textarea_message.text-danger",
        },
        {
            trigger: ".o_social_comments_modal",
            content: "Should not be able to spam",
            run: () => {
                const fourthComment = document.querySelectorAll(
                    `.o_social_comment_text[data-original-message*="${message}"]`,
                );
                if (fourthComment.length) {
                    console.error("Should not be able to spam (message detected)");
                }
            },
        },
    );

    return tourSteps;
}

registry
    .category("web_tour.tours")
    .add("social_twitter/static/tests/tours/tour_social_twitter_spam.js", {
        url: "/odoo",
        steps: () => [
            {
                trigger: '.o_app[data-menu-xmlid="social.menu_social_global"]',
                content: "Open the Social App",
                run: "click",
            },
            {
                trigger: ".o_social_stream_post_message",
                content: "Open the tweet comments",
                run: "click",
            },
            ...createReplies(
                ".o_social_comments_modal textarea.o_social_add_comment:not([data-is-comment-reply])",
            ),
        ],
    });
