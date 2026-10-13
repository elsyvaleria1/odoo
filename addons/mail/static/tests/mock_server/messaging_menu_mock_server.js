// @ts-check
import { deserializeDateTime, hasSame, now } from "@web/core/l10n/dates";

export const messagingMenuHelpers = {
    /**
     * @param {any} env
     * @param {string} tabId
     * @returns {((record: any) => boolean) | null}
     */
    _getMenuTabPredicate(env, tabId) {
        const partnerId = env.user?.partner_id;
        const isInternal = this._isInternal(env);
        switch (tabId) {
            case "bookmark":
                return (message) =>
                    Boolean(message.starred_partner_ids?.includes(partnerId));
            case "notification":
                return (message) =>
                    message.model !== "discuss.channel" &&
                    env["mail.notification"]._filter([
                        ["mail_message_id", "=", message.id],
                        ["res_partner_id", "=", partnerId],
                    ]).length > 0;
            case "chat":
                return (channel) =>
                    ["chat", "group"].includes(channel.channel_type) &&
                    !this._isMeeting(env, channel) &&
                    Boolean(this._selfMember(env, channel)?.is_pinned);
            case "meeting":
                return (channel) =>
                    channel.channel_type === "group" &&
                    this._isMeeting(env, channel) &&
                    Boolean(this._selfMember(env, channel)?.is_pinned);
            case "channel":
                return (channel) =>
                    channel.channel_type === "channel" &&
                    (Boolean(this._selfMember(env, channel)?.is_pinned) ||
                        (isInternal && this._hasNeedaction(env, channel)));
            default:
                return null;
        }
    },
    /**
     * @param {any} env
     * @param {string} tabId
     * @param {string} filterId
     * @returns {((record: any) => boolean) | null}
     */
    _getMenuTabFilterPredicate(env, tabId, filterId) {
        const partnerId = env.user?.partner_id;
        switch (`${tabId}/${filterId}`) {
            case "notification/notification_unread":
                return (message) =>
                    env["mail.notification"]._filter([
                        ["mail_message_id", "=", message.id],
                        ["res_partner_id", "=", partnerId],
                        ["is_read", "=", false],
                    ]).length > 0;
            case "chat/chat_unread":
            case "channel/channel_unread":
            case "meeting/meeting_unread":
                return (channel) => this._isUnread(env, channel);
            case "chat/chat_group":
                return (channel) => channel.channel_type === "group";
            case "channel/channel_thread":
            case "meeting/meeting_thread":
                return (channel) => Boolean(channel.parent_channel_id);
            case "meeting/meeting_today":
                return (channel) => this._isMeetingToday(env, channel);
            default:
                return null;
        }
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _isVideoCall(env, channel) {
        return channel?.default_display_mode === "video_full_screen";
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _isMeeting(env, channel) {
        return (
            this._isVideoCall(env, channel) ||
            this._isVideoCall(env, this._parentChannel(env, channel))
        );
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _parentChannel(env, channel) {
        return channel.parent_channel_id
            ? env["discuss.channel"].browse(channel.parent_channel_id)[0]
            : undefined;
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _isMeetingToday(env, channel) {
        return (
            this._isVideoCall(env, channel) &&
            hasSame(deserializeDateTime(channel.create_date), now(), "day")
        );
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _isMeetingNotOver(env, channel) {
        const meeting = this._isVideoCall(env, channel)
            ? channel
            : this._parentChannel(env, channel);
        return (
            this._isVideoCall(env, meeting) && Boolean(meeting.rtc_session_ids?.length)
        );
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _meetingDates(env, channel) {
        const meeting = this._isVideoCall(env, channel)
            ? channel
            : this._parentChannel(env, channel);
        if (!this._isVideoCall(env, meeting)) {
            return undefined;
        }
        return {
            meeting_start_dt: meeting.create_date,
            meeting_stop_dt: meeting.create_date,
        };
    },
    /** @param {any} env */
    _isInternal(env) {
        return Boolean(
            env.user && !env.user.share && !env["res.users"]._is_public(env.uid),
        );
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _selfMember(env, channel) {
        const [partner, guest] = env["res.partner"]._get_current_persona();
        if (!partner && !guest) {
            return undefined;
        }
        return env["discuss.channel.member"]._filter([
            ["channel_id", "=", channel.id],
            partner ? ["partner_id", "=", partner.id] : ["guest_id", "=", guest.id],
        ])[0];
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _isUnread(env, channel) {
        const member = this._selfMember(env, channel);
        return Boolean(
            member &&
            env["discuss.channel.member"]._compute_message_unread_counter([member.id]) >
                0,
        );
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    _hasNeedaction(env, channel) {
        return env["mail.message"]
            ._filter([
                ["model", "=", "discuss.channel"],
                ["res_id", "=", channel.id],
            ])
            .some(
                (/** @type {any} */ message) =>
                    env["mail.notification"]._filter([
                        ["mail_message_id", "=", message.id],
                        ["res_partner_id", "=", env.user?.partner_id],
                        ["is_read", "=", false],
                    ]).length > 0,
            );
    },
    /**
     * @param {any} env
     * @param {string} tabId
     * @param {string[]} [filterIds]
     * @returns {(record: any) => boolean}
     */
    getFullPredicate(env, tabId, filterIds = []) {
        const predicate = this._getMenuTabPredicate(env, tabId);
        if (!predicate) {
            throw new Error(`unknown messaging menu tab "${tabId}"`);
        }
        const filters = filterIds.map((filterId) => {
            const filter = this._getMenuTabFilterPredicate(env, tabId, filterId);
            if (!filter) {
                throw new Error(
                    `unknown messaging menu filter "${filterId}" for tab "${tabId}"`,
                );
            }
            return filter;
        });
        return (record) =>
            predicate(record) && filters.every((filter) => filter(record));
    },
    /**
     * @param {any} env
     * @param {any} channel
     */
    isImportantChannel(env, channel) {
        const member = this._selfMember(env, channel);
        const unread =
            member?.is_pinned && !member.mute_until_dt && this._isUnread(env, channel);
        const isInternal = this._isInternal(env);
        return Boolean(unread || (isInternal && this._hasNeedaction(env, channel)));
    },
};
