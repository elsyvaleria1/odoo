/** @odoo-module native */
import { ThreadAction } from "@mail/core/common/thread_actions";
import { patch } from "@web/core/utils/patch";

patch(ThreadAction.prototype, {
    _condition({ action, thread }) {
        const requiredActions = ["close", "fold-chat-window", "expand-discuss"];
        if (
            thread?.channel_type === "ai_chat" &&
            !requiredActions.includes(action.id)
        ) {
            return false;
        }
        return super._condition(...arguments);
    },
});
