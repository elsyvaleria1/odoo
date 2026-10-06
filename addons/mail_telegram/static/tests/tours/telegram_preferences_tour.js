// @ts-check
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("mail_telegram_preferences", {
    steps: () => [
        {
            content: "Open user account menu",
            trigger: ".o_user_menu button",
            run: "click",
        },
        {
            content: "Open preferences",
            trigger: "[data-menu=preferences]",
            run: "click",
        },
        {
            content: "The delivery status says notifications are delivered",
            trigger: ".modal div[name=telegram_notify_state]:contains('Delivering')",
        },
        {
            // the dialog scrolls to the field when it is clicked, and a scroll
            // after the dropdown opened closes it: scroll first, as a person
            // does before typing
            content: "Bring the destination into view",
            trigger: ".modal div[name=telegram_notify_chat_id]",
            async run({ anchor }) {
                anchor.scrollIntoView({ block: "center" });
                await new Promise((resolve) => setTimeout(resolve, 300));
            },
        },
        {
            content: "Look the work phone up by its number",
            trigger: ".modal div[name=telegram_notify_chat_id] input",
            run: "edit 98765",
        },
        {
            content: "Choose the work phone's chat",
            trigger: ".o-autocomplete--dropdown-item > a:contains('+525598765432')",
            run: "click",
        },
        {
            content: "Save the preferences, which reloads the page",
            trigger: ".modal button[name=action_save_preferences]",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "The web client is back",
            trigger: ".o_user_menu button",
        },
    ],
});
