// @ts-check
/** @odoo-module native */
import { Message } from "@mail/core/common/message_model";
import { fields } from "@mail/core/common/record";
import { patch } from "@web/core/utils/patch";
/** @type {Partial<import("models").Message> & ThisType<import("models").Message>} */
const messagePatch = {
    setup() {
        super.setup();
        this.hasNewMessageSeparator = fields.Attr(false, {
            /** @this {import("models").Message} */
            compute() {
                return (
                    this.thread?.channel?.self_member_id?.new_message_separator ===
                    this.id
                );
            },
        });
        this.threadAsFirstUnread = fields.One("discuss.channel", {
            inverse: "firstUnreadMessage",
        });
    },
    // the seen states below are getters, not computed fields: computes are
    // eager, and these walk the channel's members for every loaded message
    // while only the seen indicator of a self-authored message reads them
    /** @returns {boolean} */
    get hasEveryoneSeen() {
        return Boolean(this.thread?.membersThatCanSeen.every((m) => m.hasSeen(this)));
    },
    /** @returns {boolean} */
    get hasSomeoneFetched() {
        if (this.isSelfAuthored && this.thread) {
            return this.thread.channel?.maxFetchedMessageIdByOthers >= Number(this.id);
        }
        return Boolean(
            this.thread?.channel?.channel_member_ids?.some(
                (m) =>
                    m.persona?.notEq(this.author) &&
                    m.fetched_message_id?.id >= this.id,
            ),
        );
    },
    /** @returns {boolean} */
    get hasSomeoneSeen() {
        if (this.isSelfAuthored && this.thread) {
            return this.thread.channel?.maxSeenMessageIdByOthers >= Number(this.id);
        }
        return Boolean(
            this.thread?.membersThatCanSeen.some(
                (m) => m.persona?.notEq(this.author) && m.hasSeen(this),
            ),
        );
    },
    /** @returns {boolean} */
    get isMessagePreviousToLastSelfMessageSeenByEveryone() {
        const lastSeen = this.thread?.channel?.lastSelfMessageSeenByEveryone;
        return Boolean(lastSeen) && this.id < lastSeen.id;
    },
    /** @returns {import("models").ChannelMember[]} */
    get channelMemberHaveSeen() {
        return this.thread.membersThatCanSeen.filter(
            (m) => m.hasSeen(this) && m.persona.notEq(this.author),
        );
    },
};
patch(Message.prototype, messagePatch);
