/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";
import { onWillDestroy, t } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class KnowledgeCommentCreatorComposer extends Composer {
    static props = { ...Composer.props, onCreateThreadCallback: t.any().optional() };

    setup() {
        super.setup();
        this.commentsService = useService("knowledge.comments");
        this.newThread = undefined;
        onWillDestroy(() => {
            this.props.onCreateThreadCallback?.(this.newThread);
        });
    }

    /**
     * @override
     */
    async _sendMessage(value, postData) {
        this.newThread = await this.commentsService.createThreadAndPost(
            value,
            postData,
        );
        this.clear();
    }
}
