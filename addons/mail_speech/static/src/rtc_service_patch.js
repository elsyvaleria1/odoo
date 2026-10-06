/** @odoo-module native */
import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { patch } from "@web/core/utils/patch";

patch(Rtc.prototype, {
    /** @param {import("models").DiscussChannel} [channel] */
    async leaveCall(channel = this.state.channel) {
        const recording = this.store.env.services["discuss.call_recording"];
        if (recording?.state.channelId === channel?.id) {
            await recording.stop();
        }
        return super.leaveCall(channel);
    },
});
