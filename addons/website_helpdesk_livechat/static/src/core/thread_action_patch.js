/** @odoo-module native */
import { ThreadAction } from "@mail/core/common/thread_actions";
import { patch } from "@web/core/utils/patch";

patch(ThreadAction.prototype, {
    _condition({ action, owner, store, thread }) {
        if (
            action.id === "create-ticket" &&
            store.helpdesk_livechat_active &&
            thread?.isLivechat &&
            store.has_access_create_ticket &&
            !owner.isChannelActionList
        ) {
            return true;
        }
        return super._condition(...arguments);
    },
});
