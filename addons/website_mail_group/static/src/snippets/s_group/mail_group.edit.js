/** @odoo-module native */
import { MailGroup } from "@mail_group/interactions/mail_group";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class MailGroupEdit extends Interaction {
    static selector = MailGroup.selector;
    dynamicContent = {
        _root: {
            "t-att-class": () => ({
                "d-none": false,
            }),
        },
    };
}

registry.category("public.interactions.edit").add("website_mail_group.mail_group", {
    Interaction: MailGroupEdit,
});
