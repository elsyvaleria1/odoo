// @ts-check
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("sidebar_in_public_page_tour", {
    steps: () => [
        {
            trigger: ".o-mail-DiscussContent-header [title='Channel 1']",
        },
        {
            trigger:
                ".o-mail-Discuss .o-mail-MessagingMenuItem:contains(Channel 1):has(.o-mail-NotificationItem.o-active)",
        },
        {
            trigger: ".o-mail-Discuss .o-mail-NotificationItem:contains(Channel 2)",
            run: "click",
        },
        {
            trigger: ".o-mail-DiscussContent-header [title='Channel 2']",
        },
        {
            trigger:
                ".o-mail-Discuss .o-mail-MessagingMenuItem:contains(Channel 2):has(.o-mail-NotificationItem.o-active)",
            run() {
                history.back();
            },
        },
        {
            trigger: ".o-mail-DiscussContent-header [title='Channel 1']",
        },
        {
            trigger:
                ".o-mail-Discuss .o-mail-MessagingMenuItem:contains(Channel 1):has(.o-mail-NotificationItem.o-active)",
            run() {
                history.forward();
            },
        },
        {
            trigger: ".o-mail-DiscussContent-header [title='Channel 2']",
        },
        {
            trigger:
                ".o-mail-Discuss .o-mail-MessagingMenuItem:contains(Channel 2):has(.o-mail-NotificationItem.o-active)",
        },
        {
            content: "Open channel actions",
            trigger:
                ".o-mail-Discuss .o-mail-MessagingMenuItem:contains(Channel 2):has(.o-mail-NotificationItem.o-active)",
            run: "hover && click [title='Channel Actions']",
        },
        {
            trigger: ".o-dropdown-item:contains('Invite People')",
            run: "click",
        },
    ],
});
