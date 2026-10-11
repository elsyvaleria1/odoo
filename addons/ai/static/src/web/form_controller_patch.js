/** @odoo-module native */
import { useEventBus, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form";

patch(FormController.prototype, {
    setup() {
        super.setup();
        this.bus = useEventBus();
        this.aiChatLauncher = useService("aiChatLauncher");
        const openAiChat = (ev) => this.openAiChat(ev.detail.origin);
        useLayoutEffect(
            () => {
                this.bus.addEventListener("AI:OPEN_AI_CHAT", openAiChat);
                return () =>
                    this.bus.removeEventListener("AI:OPEN_AI_CHAT", openAiChat);
            },
            () => [],
        );
    },

    async openAiChat(callerComponentName) {
        if (!this.mailStore || !(await this.model.root.save())) {
            return;
        }
        this.aiChatLauncher.launchAIChat({
            callerComponentName,
            channelTitle: this.displayName(),
            recordModel: this.model.root.resModel,
            recordId: this.model.root.resId,
            originalRecordData: this.model.root.data,
            originalRecordFields: this.model.root.fields,
            aiChatSourceId: this.model.root.resId,
        });
    },
});
