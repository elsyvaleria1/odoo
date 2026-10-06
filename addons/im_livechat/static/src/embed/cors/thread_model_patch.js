/** @odoo-module native */
import { expirableStorage } from "@im_livechat/core/common/expirable_storage";
import { GUEST_TOKEN_STORAGE_KEY } from "@im_livechat/embed/common/store_service_patch";
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { patch } from "@web/core/utils/patch";
import { url } from "@web/core/utils/urls";

patch(DiscussChannel.prototype, {
    get transcriptUrl() {
        return url(`/im_livechat/cors/download_transcript/${this.id}`);
    },

    get transcriptGuestToken() {
        return expirableStorage.getItem(GUEST_TOKEN_STORAGE_KEY);
    },
});
