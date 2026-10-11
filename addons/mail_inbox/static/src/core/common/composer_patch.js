/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";

patch(Composer.prototype, {
    get postsOnEnter() {
        return this.thread?.channel?.channel_type !== "email" && super.postsOnEnter;
    },
});
