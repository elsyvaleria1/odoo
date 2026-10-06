/** @odoo-module native */
import "@mail/core/public_web/store_service_patch";

import { Store } from "@mail/core/common/store_service";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

/** @type {import("models").Store} */
const storePatch = {
    setup() {
        super.setup(...arguments);
        this.livechatChannels = this.makeCachedFetchData("im_livechat.channel");
        this.livechatSelfExpertises = this.makeCachedFetchData(
            "/im_livechat/fetch_self_expertise",
        );
        this.has_access_livechat = false;
    },
    /**
     * @override
     */
    onStarted() {
        super.onStarted(...arguments);
        if (this.discuss.isActive && this.has_access_livechat) {
            this.livechatChannels.fetch();
            this.livechatSelfExpertises.fetch();
        }
    },
    /** @param {{exclude?: import("models").DiscussChannel}} [options] */
    async goToOldestUnreadLivechatThread({ exclude } = {}) {
        const { channel_id } = await this.fetchStoreData(
            "/im_livechat/oldest_unread_livechat",
            { exclude_ids: exclude ? [Number(exclude.id)] : [] },
            { requestData: true },
        );
        const oldestUnreadThread =
            channel_id && this["discuss.channel"].get(channel_id);
        if (!oldestUnreadThread) {
            return false;
        }
        if (this.discuss.isActive) {
            oldestUnreadThread.setAsDiscussThread();
            return true;
        }
        await this.chatHub.initPromise;
        const chatWindow = this.ChatWindow.insert({ thread: oldestUnreadThread });
        chatWindow.open({ focus: true, jumpToNewMessage: true });
        return true;
    },
    get livechatStatusButtons() {
        return [
            {
                label: _t("In progress"),
                status: "in_progress",
                icon: "fa-solid fa-comments",
            },
            {
                label: _t("Waiting for customer"),
                status: "waiting",
                icon: "fa-solid fa-hourglass-start",
            },
            {
                label: _t("Looking for help"),
                status: "need_help",
                icon: "fa-solid fa-exclamation-circle fa-lg",
            },
        ];
    },
};
patch(Store.prototype, storePatch);
