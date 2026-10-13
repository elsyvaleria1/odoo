/** @odoo-module native */
import { Message } from "@mail/core/common/message";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
    },

    /** @override */
    async openRecord() {
        if (this.message.model === "knowledge.article.thread") {
            const [articleThread] = await this.orm.searchRead(
                "knowledge.article.thread",
                [["id", "=", this.message.thread.id]],
                ["article_id"],
            );
            this.action.doAction({
                type: "ir.actions.act_window",
                res_id: articleThread.article_id[0],
                res_model: "knowledge.article",
                views: [[false, "form"]],
            });
            return;
        }
        super.openRecord();
    },
});
