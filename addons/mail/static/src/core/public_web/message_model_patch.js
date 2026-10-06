// @ts-check
/** @odoo-module native */
import { Message } from "@mail/core/common/message_model";
import { fields } from "@mail/model/misc";
import { patch } from "@web/core/utils/patch";

/** @type {Partial<import("models").Message> & ThisType<import("models").Message>} */
const messagePatch = {
    setup() {
        super.setup();
        this.messagingMenuTabsAsMessages = fields.Many("MessagingMenuTab", {
            inverse: "messages",
            /** @this {import("models").Message} */
            compute() {
                return (this.store.messagingMenu?.allTabs ?? []).filter((tab) =>
                    tab.includesMessage(this),
                );
            },
        });
    },
};
patch(Message.prototype, messagePatch);
