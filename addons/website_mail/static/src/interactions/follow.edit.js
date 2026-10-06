/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Follow } from "@website_mail/interactions/follow";

const FollowEdit = (I) =>
    class extends I {
        dynamicContent = {};
    };

registry.category("public.interactions.edit").add("website_mail.follow", {
    Interaction: Follow,
    mixin: FollowEdit,
});
