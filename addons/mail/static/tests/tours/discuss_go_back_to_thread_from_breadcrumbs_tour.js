// @ts-check
import { registry } from "@web/core/registry";

registry
    .category("web_tour.tours")
    .add("discuss_go_back_to_thread_from_breadcrumbs.js", {
        steps: () => [
            {
                content: "The legacy Inbox link lands on the Notifications tab",
                trigger:
                    ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='notification'].active",
            },
            {
                trigger: ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='channel']",
                run: "click",
            },
            {
                trigger:
                    ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='channel'].active",
            },
            {
                trigger:
                    ".o-mail-Discuss .o-mail-MessagingMenu-action[data-action='browse_channels']",
                run: "click",
            },
            {
                content: "Wait for the channel list to replace Discuss",
                trigger: ".o_breadcrumb .breadcrumb-item a",
            },
            { trigger: ".o_breadcrumb .breadcrumb-item a", run: "click" },
            {
                content: "Discuss comes back on the tab it was left on",
                trigger:
                    ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='channel'].active",
            },
        ],
    });
