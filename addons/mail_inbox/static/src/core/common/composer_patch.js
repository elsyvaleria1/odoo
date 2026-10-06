/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";

patch(Composer.prototype, {
    // everything written in an email conversation is mailed to the
    // correspondent: Enter is a new line, as in a mail client
    get postsOnEnter() {
        return this.thread?.channel?.channel_type !== "email" && super.postsOnEnter;
    },
});
