import { contains } from "@web/../tests/utils";
import { registry } from "@web/core/registry";

const cannedResponseButtonSelector = "button[title='Insert a Canned response']";

registry.category("web_tour.tours").add("portal_composer_actions_tour_internal_user", {
    steps: () => [
        {
            trigger: `#chatterRoot:shadow .o-mail-Composer ${cannedResponseButtonSelector}`,
            run: "click",
        },
        {
            trigger: "#chatterRoot:shadow .o-mail-Composer-input",
            async run() {
                await contains(".o-mail-Composer-input", {
                    value: "::",
                    target: document.querySelector("#chatterRoot").shadowRoot,
                });
            },
        },
        {
            trigger:
                "#chatterRoot:shadow .o-mail-Composer-suggestion:contains(Hello, how may I help you?)",
        },
    ],
});

registry.category("web_tour.tours").add("portal_composer_actions_tour_portal_user", {
    steps: () => [
        {
            trigger: `#chatterRoot:shadow .o-mail-Composer:not(:has(${cannedResponseButtonSelector}))`,
        },
    ],
});
