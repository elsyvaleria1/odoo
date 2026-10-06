/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { DiscussApp } from "@mail/core/public_web/discuss_app_model";
import { readLocalStorageItem } from "@mail/utils/common/local_storage";
import { patch } from "@web/core/utils/patch";

export const LIVECHAT_INFO_DEFAULT_OPEN_LS = "im_livechat.isInfoPanelOpenByDefault";

patch(DiscussApp.prototype, {
    setup(env) {
        super.setup(...arguments);
        this.lastThread = fields.One("discuss.channel");
        this.isLivechatInfoPanelOpenByDefault = fields.Attr(true, {
            compute() {
                return (
                    readLocalStorageItem(this.store, LIVECHAT_INFO_DEFAULT_OPEN_LS) !==
                    "false"
                );
            },
        });
    },

    shouldDisableMemberPanelAutoOpenFromClose(nextActiveAction) {
        if (nextActiveAction?.id === "livechat-info") {
            return false;
        }
        return super.shouldDisableMemberPanelAutoOpenFromClose(...arguments);
    },

    _threadOnUpdate() {
        if (
            this.lastThread?.notEq(this.thread) &&
            (this.lastThread.livechat_status === "need_help" ||
                this.lastThread.unpinOnThreadSwitch)
        ) {
            this.lastThread.isLocallyPinned = false;
        }
        if (
            this.thread?.livechat_status === "need_help" &&
            !this.thread.self_member_id
        ) {
            this.thread.isLocallyPinned = true;
        }
        this.lastThread = this.thread;
        super._threadOnUpdate();
    },
});
