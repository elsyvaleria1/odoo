/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(Composer.prototype, {
    onKeydown(ev) {
        super.onKeydown(ev);
        if (
            ev.key === "Tab" &&
            !this.props.composer.composerText &&
            this.displayNextLivechatHint()
        ) {
            ev.stopPropagation();
            this.store.goToOldestUnreadLivechatThread({ exclude: this.thread.channel });
        }
    },
    get placeholder() {
        if (this.displayNextLivechatHint() && this.props.composer.isFocused) {
            return _t("Tab to next livechat");
        }
        return super.placeholder;
    },
    displayNextLivechatHint() {
        const channel = this.thread?.channel;
        if (!channel?.isLivechat) {
            return false;
        }
        const tab = this.store.messagingMenu.livechatTab;
        return tab.counter - (channel.in(tab.channelsWithCounter) ? 1 : 0) > 0;
    },
});
