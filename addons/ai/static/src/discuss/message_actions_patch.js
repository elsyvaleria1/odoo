/** @odoo-module native */
import { unwrapContents } from "@html_editor/utils/dom";
import {
    MessageAction,
    registerMessageAction,
} from "@mail/core/common/message_actions";
import { _t } from "@web/core/translation";
import { setElementContent } from "@web/core/utils/dom/html";
import { patch } from "@web/core/utils/patch";

registerMessageAction("insertToComposer", {
    condition: ({ message, store, thread }) =>
        !!thread?.aiSpecialActions?.insert &&
        // after a reload aiInsertButtonTarget and aiChatSource are both undefined, which would
        // make the next condition true and wrongly show the button
        store.aiInsertButtonTarget &&
        (store.aiInsertButtonTarget === thread.aiChatSource || store.env.isSmall) &&
        !message.isSelfAuthored,
    name: _t("Use this"),
    onSelected: ({ message, store, thread }) => {
        const fragment = document.createDocumentFragment();
        const content_root = document.createElement("span");
        content_root.setAttribute("InsertorId", "AIInsertion");
        setElementContent(content_root, message.body);
        const paragraphElements = content_root.querySelectorAll("p");
        if (paragraphElements.length === 1) {
            unwrapContents(paragraphElements[0]);
        }
        fragment.appendChild(content_root);
        thread.aiSpecialActions.insert(fragment);
        if (store.env.isSmall) {
            thread.closeChatWindow();
        }
    },
    sequence: 10,
});
registerMessageAction("send-message-direct", {
    condition: ({ message, thread }) =>
        !!thread?.aiSpecialActions?.sendMessage && !message.isSelfAuthored,
    name: _t("Send as Message"),
    onSelected: ({ message, thread }) =>
        thread.aiSpecialActions.sendMessage(message.body),
    sequence: 20,
});
registerMessageAction("log-note-direct", {
    condition: ({ message, thread }) =>
        !!thread?.aiSpecialActions?.logNote && !message.isSelfAuthored,
    name: _t("Log as Note"),
    onSelected: ({ message, thread }) => thread.aiSpecialActions.logNote(message.body),
    sequence: 25,
});

patch(MessageAction.prototype, {
    _condition({ thread }) {
        const requiredActions = [
            "insertToComposer",
            "copy-message",
            "send-message-direct",
            "log-note-direct",
        ];
        if (thread?.channel_type === "ai_chat") {
            if (!requiredActions.includes(this.id)) {
                return false;
            }
            if (this.id === "copy-message") {
                return true;
            }
        }
        return super._condition(...arguments);
    },
    _sequence({ thread }) {
        if (this.id === "copy-message" && thread?.channel_type === "ai_chat") {
            return 50;
        }
        return super._sequence(...arguments);
    },
});
