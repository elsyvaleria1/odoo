/** @odoo-module native */
import { ChatWindow } from "@mail/core/common/chat_window_model";
import { rpc } from "@web/core/network";
import { patch } from "@web/core/utils/patch";

patch(ChatWindow.prototype, {
    computeCanShow() {
        if (this.store.aiInsertButtonTarget && this.store.discuss.isActive) {
            return this.thread?.channel_type === "ai_chat";
        }
        return super.computeCanShow();
    },
    async _onClose() {
        const thread = this.thread;
        if (thread?.ai_agent_id) {
            await rpc("/ai/close_ai_chat", { channel_id: thread.id });
        }
        await super._onClose(...arguments);
    },
});
