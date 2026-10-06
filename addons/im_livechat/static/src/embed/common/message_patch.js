/** @odoo-module native */
import { Message } from "@mail/core/common/message";
import { t } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { url } from "@web/core/utils/urls";

Message.props.isTypingMessage = t.any().optional();

patch(Message.prototype, {
    setup() {
        super.setup();
        this.url = url;
    },

    get quickActionCount() {
        return this.props.thread?.isLivechat ? 3 : super.quickActionCount;
    },

    /**
     * @param {import("@im_livechat/core/common/chatbot_step_model").StepAnswer} answer
     */
    answerChatbot(answer) {
        if (this.props.message.disableChatbotAnswers) {
            return;
        }
        this.props.message.disableChatbotAnswers = true;
        return this.props.message.thread.post(
            answer.name,
            {},
            { selected_answer_id: answer.id },
        );
    },
});
