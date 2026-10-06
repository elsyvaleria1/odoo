// @ts-check
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("can_create_channel_from_form_view", {
    steps: () => [
        {
            trigger: ".o-mail-Discuss .o-mail-NotificationItem-name:contains(OdooBot)",
            run: "click",
        },
        {
            trigger: ".o-mail-DiscussContent-threadName[title='OdooBot']",
        },
        {
            trigger: ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='channel']",
            run: "click",
        },
        {
            trigger:
                ".o-mail-Discuss .o-mail-MessagingMenu-action[title='Browse Channels']",
            run: "click",
        },
        {
            trigger: ".o_control_panel_main_buttons button:contains('New')",
            run: "click",
        },
        {
            trigger: "div[name='name'] input",
            run: "edit Test channel",
        },
        {
            trigger: ".breadcrumb-item:first",
            run: "click",
        },
        {
            trigger:
                ".o-mail-Discuss .o-mail-MessagingMenu-tab.active[data-id='channel']",
        },
        {
            trigger:
                ".o-mail-Discuss .o-mail-NotificationItem-name:contains('Test channel')",
        },
    ],
});
