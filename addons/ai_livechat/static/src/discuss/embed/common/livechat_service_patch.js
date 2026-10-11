/** @odoo-module native */
import { LivechatService } from "@im_livechat/embed/common/livechat_service";
import { patch } from "@web/core/utils/patch";

patch(LivechatService.prototype, {
    getSessionExtraParams(thread, options) {
        const extraParams = super.getSessionExtraParams(thread, options);
        extraParams["ai_agent_id"] =
            options.ai_agent_id ?? this.store.livechat_rule?.ai_agent_id;
        return extraParams;
    },
});
