/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { toRaw } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(DiscussChannel.prototype, {
    setup() {
        super.setup();
        this.wa_account_id = fields.One("whatsapp.account");
    },
    get importantCounter() {
        if (this.channel_type === "whatsapp") {
            return (
                this.self_member_id?.message_unread_counter ||
                this.message_needaction_counter
            );
        }
        return super.importantCounter;
    },
    get autoOpenChatWindowOnNewMessage() {
        return this.channel_type === "whatsapp" || super.autoOpenChatWindowOnNewMessage;
    },
    get canLeave() {
        return this.channel_type !== "whatsapp" && super.canLeave;
    },
    get allowedToUnpinChannelTypes() {
        return [...super.allowedToUnpinChannelTypes, "whatsapp"];
    },
    get avatarUrl() {
        if (this.channel_type === "whatsapp" && this.correspondent) {
            return this.correspondent.avatarUrl;
        }
        return super.avatarUrl;
    },

    get isChatChannel() {
        return this.channel_type === "whatsapp" || super.isChatChannel;
    },
    /** @override */
    get imStatusMember() {
        return this.channel_type === "whatsapp"
            ? this.correspondent
            : super.imStatusMember;
    },

    get whatsappChannelValidUntilDatetime() {
        if (!this.whatsapp_channel_valid_until) {
            return undefined;
        }
        return toRaw(deserializeDateTime(this.whatsapp_channel_valid_until));
    },
});
