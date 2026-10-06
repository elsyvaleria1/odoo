/** @odoo-module native */
import { YoutubeUploadField } from "@social_youtube/js/social_youtube_upload_field";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(YoutubeUploadField.prototype, {
    /**
     * When the user selects a file, as we are in demo mode, the video will not be uploaded.
     * Display a toaster to the user to inform them cannot upload video in demo mode.
     *
     * @private
     */
    async _onFileChanged() {
        this.notification.add(_t("You cannot upload videos in demo mode."), {
            type: "info",
        });
    },
});
