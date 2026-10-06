/** @odoo-module native */
import { MessagingMenu } from "@mail/core/public_web/messaging_menu/messaging_menu";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        useLayoutEffect(
            (isLivechatTab, hasAccess) => {
                if (isLivechatTab && hasAccess) {
                    this.store.livechatChannels.fetch();
                    this.store.livechatSelfExpertises.fetch();
                }
            },
            () => [
                Boolean(this.activeTab?.eq(this.store.messagingMenu.livechatTab)),
                this.store.has_access_livechat,
            ],
        );
    },
});
