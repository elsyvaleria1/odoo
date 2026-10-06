import { registry } from "@web/core/registry";

registry
    .category("web_tour.tours")
    .add("im_livechat.looking_for_help_discuss_category_tour", {
        steps: () => [
            {
                trigger:
                    ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='livechat']",
                run: "click",
            },
            {
                trigger:
                    ".o-mail-MessagingMenu-filter[data-filter='livechat_need_help']",
                run: "click",
            },
            {
                trigger:
                    ".o-mail-MessagingMenu-filter.o-active[data-filter='livechat_need_help']",
            },
            {
                trigger: ".o-mail-MessagingMenuItem:contains(Visitor Accounting)",
            },
            {
                trigger:
                    ".o-mail-MessagingMenuItem:contains(Visitor Sales) .o-mail-starred",
            },
            {
                trigger:
                    ".o-mail-MessagingMenuItem:contains(Visitor Accounting):not(:has(.o-mail-starred))",
            },
            {
                trigger: ".o-mail-MessagingMenuItem:contains(Visitor Accounting)",
                run: "hover && click .o-mail-MessagingMenuItem:contains(Visitor Accounting) [title='Chat Actions']",
            },
            {
                trigger:
                    ".o-mail-Discuss:has(.o-mail-MessagingMenuItem:contains(Visitor Accounting))",
            },
            {
                trigger: "button[name='livechat-status']",
                run: "hover",
            },
            {
                trigger:
                    ".o-livechat-LivechatStatusSelection-Label:contains(In progress)",
                run: "click",
            },
            {
                trigger:
                    ".o-mail-Discuss:not(:has(.o-mail-MessagingMenuItem:contains(Visitor Accounting)))",
            },
        ],
    });
