import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("mail_group_subscribe_in_place", {
    steps: () => [
        {
            content: "the group offers to subscribe",
            trigger: ".o_mail_group_row:contains(PN Joinable) button[value=subscribe]",
            run() {
                window.subscribeMarker = true;
            },
        },
        {
            content: "subscribe",
            trigger: ".o_mail_group_row:contains(PN Joinable) button[value=subscribe]",
            run: "click",
        },
        {
            content: "it now offers to unsubscribe, and counts one member, in place",
            trigger:
                "body:not(:has(form[aria-busy])) .o_mail_group_row:contains(PN Joinable):has(.o_mg_members_count:contains(1)) button[value=unsubscribe]",
            run() {
                if (!window.subscribeMarker) {
                    throw new Error("the groups page was reloaded");
                }
            },
        },
    ],
});
