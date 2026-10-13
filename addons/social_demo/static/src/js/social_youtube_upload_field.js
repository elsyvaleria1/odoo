/** @odoo-module native */
import { YoutubeUploadField } from "@social_youtube/js/social_youtube_upload_field";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(YoutubeUploadField.prototype, {
    /** @private */
    async _onFileChanged() {
        this.notification.add(_t("You cannot upload videos in demo mode."), {
            type: "info",
        });
    },
});
