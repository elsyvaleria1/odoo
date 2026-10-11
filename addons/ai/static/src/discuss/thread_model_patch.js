/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

const AI_PROMPT_BUTTONS = "ai.thread.prompt_buttons.";

patch(DiscussChannel.prototype, {
    setup() {
        super.setup();
        this.ai_prompt_buttons = fields.Many("ai.prompt.button", {
            inverse: "thread_id",
            compute() {
                const raw = browser.localStorage.getItem(
                    AI_PROMPT_BUTTONS.concat(this.id),
                );
                if (!raw || raw === "undefined") {
                    return [];
                }
                try {
                    return JSON.parse(raw);
                } catch {
                    return [];
                }
            },
        });
    },
    async closeChatWindow(options = {}) {
        await super.closeChatWindow(options);
        browser.localStorage.removeItem(AI_PROMPT_BUTTONS.concat(this.id));
    },
    get avatarUrl() {
        if (this.channel_type === "ai_chat" && this.correspondent) {
            return this.correspondent.avatarUrl;
        }

        return super.avatarUrl;
    },
    computeCorrespondent() {
        const correspondent = super.computeCorrespondent();
        if (
            ["ai_composer", "ai_chat"].includes(this.channel_type) &&
            correspondent?.persona?.eq(this.store.self)
        ) {
            return undefined;
        }
        return correspondent;
    },
});
