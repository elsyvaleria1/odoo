/** @odoo-module native */
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(WebChatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.action = useService("action");
    },

    sendWhatsapp() {
        const send = async (thread) => {
            await new Promise((resolve) => {
                this.action.doAction(
                    {
                        type: "ir.actions.act_window",
                        name: _t("Send WhatsApp Message"),
                        res_model: "wizard.whatsapp.message.send",
                        view_mode: "form",
                        views: [[false, "form"]],
                        target: "new",
                        context: {
                            active_model: thread.model,
                            active_id: thread.id,
                        },
                    },
                    { onClose: resolve },
                );
            });
            this.store.Thread.insert({
                model: this.props.threadModel,
                id: this.props.threadId,
            }).fetchNewMessages();
        };
        if (this.state.thread.id) {
            send(this.state.thread);
        } else {
            this.onThreadCreated = send;
            this.props.saveRecord?.();
        }
    },
});
