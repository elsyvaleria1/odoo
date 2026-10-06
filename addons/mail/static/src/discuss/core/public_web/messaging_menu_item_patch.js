// @ts-check
/** @odoo-module native */
import { CountryFlag } from "@mail/core/common/country_flag";
import { ImStatus } from "@mail/core/common/im_status";
import { ThreadIcon } from "@mail/core/common/thread_icon";
import {
    MessagingMenuItem,
    messagingMenuItemProps,
} from "@mail/core/public_web/messaging_menu/messaging_menu_item";
import { ChannelActionList } from "@mail/discuss/core/public_web/channel_action_list";
import { t } from "@odoo/owl";
import {
    DATE_MED_WITH_WEEKDAY,
    hasSame,
    now,
    TIME_SIMPLE,
    toLocaleString,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

Object.assign(MessagingMenuItem.components, {
    ChannelActionList,
    CountryFlag,
    ImStatus,
    ThreadIcon,
});
Object.assign(messagingMenuItemProps, { channel: t.any().optional() });

patch(MessagingMenuItem.prototype, {
    get hasActions() {
        return Boolean(this.channel) || super.hasActions;
    },
    get actionsTitle() {
        if (!this.channel) {
            return super.actionsTitle;
        }
        return this.channel.isChatChannel ? _t("Chat Actions") : _t("Channel Actions");
    },
    /** @returns {import("models").DiscussChannel|undefined} */
    get channel() {
        return this.props.channel;
    },
    /** @returns {import("models").Message|undefined} */
    get channelPreviewMessage() {
        const channel = this.channel;
        if (!channel) {
            return undefined;
        }
        return channel.isChatChannel ||
            (channel.typePolicy.notify_opted_in_only &&
                channel.needactionMessages.length === 0)
            ? channel.newestPersistentOfAllMessage
            : channel.needactionMessages.at(-1);
    },
    get isOpenInDiscuss() {
        if (!this.channel) {
            return super.isOpenInDiscuss;
        }
        return Boolean(
            this.store.discuss?.isActive && this.channel.eq(this.store.discuss.thread),
        );
    },
    /** When the channel's meeting starts: its time, with the day unless today. */
    get meetingStartText() {
        const start = this.channel?.meeting_start_dt;
        if (!start) {
            return "";
        }
        return hasSame(start, now(), "day")
            ? _t("@ %(time)s", { time: toLocaleString(start, TIME_SIMPLE) })
            : _t("@ %(date)s", {
                  date: toLocaleString(start, {
                      ...DATE_MED_WITH_WEEKDAY,
                      ...TIME_SIMPLE,
                  }),
              });
    },
    get itemName() {
        return this.channel?.displayName ?? super.itemName;
    },
    get itemPreviewText() {
        if (!this.channel) {
            return super.itemPreviewText;
        }
        return this.channelPreviewMessage?.previewText ?? "";
    },
    get canUnpin() {
        const channel = this.channel;
        return Boolean(
            channel?.canUnpin && channel.self_member_id?.message_unread_counter === 0,
        );
    },
    get notificationItemProps() {
        const channel = this.channel;
        if (!channel) {
            return super.notificationItemProps;
        }
        const message = this.channelPreviewMessage;
        return {
            thread: channel,
            counter: channel.importantCounter,
            datetime: message?.datetime,
            iconSrc: channel.avatarUrl,
            important: channel.importantCounter,
            hasMarkAsReadButton: channel.isUnread,
            isActive: this.props.isActive || this.isOpenInDiscuss,
            muted: channel.isMuted ? 2 : !channel.isUnread ? 1 : 0,
            nameMaxLine: 1,
            textMaxLine: 2,
            onSwipeRight:
                this.hasTouch() && channel.isUnread
                    ? {
                          action: () => this.props.onClick({ isMarkAsRead: true }),
                          icon: "fa-check-circle",
                          bgColor: "bg-success",
                      }
                    : undefined,
            onSwipeLeft:
                this.hasTouch() && this.canUnpin
                    ? {
                          action: () => channel.unpin(),
                          icon: "fa-times-circle",
                          bgColor: "bg-danger",
                      }
                    : undefined,
            onClick: (/** @type {boolean} */ isMarkAsRead) =>
                this.props.onClick({ isMarkAsRead }),
        };
    },
});
