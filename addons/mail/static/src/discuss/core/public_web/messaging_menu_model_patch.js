// @ts-check
/** @odoo-module native */
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { compareMeetings } from "@mail/discuss/core/public_web/meeting_compare";
import { MessagingMenuEmptyChannel } from "@mail/discuss/core/public_web/messaging_menu_empty_channel";
import { compareChannels } from "@mail/discuss/core/public_web/messaging_menu_tab_model_patch";
import { fields } from "@mail/model/misc";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.CHAT = "chat";
MENU_TABS.CHANNEL = "channel";
MENU_TABS.MEETING = "meeting";

/** @type {Partial<import("models").MessagingMenu> & ThisType<import("models").MessagingMenu>} */
const messagingMenuPatch = {
    setup() {
        super.setup();
        this.chatTab = fields.One("MessagingMenuTab", {
            /** @this {import("models").MessagingMenu} */
            compute() {
                const { command } = this.store.env.services;
                const actions = [];
                if (this.store.selfIsInternalUser && command) {
                    actions.push({
                        id: "new_chat",
                        icon: "fa-solid fa-pen-to-square",
                        text: _t("New Message"),
                        onClick: () => command.openMainPalette({ searchValue: "@" }),
                    });
                }
                return {
                    id: MENU_TABS.CHAT,
                    recordType: "discuss.channel",
                    channelTypes: ["chat", "group"],
                    /** @param {import("models").DiscussChannel} channel */
                    holdsChannel: (channel) => !channel.isMeetingOrMeetingChild,
                    /** @param {import("models").DiscussChannel} channel */
                    includesChannel: (channel) =>
                        Boolean(channel.self_member_id?.is_pinned),
                    icon: "oi oi-users",
                    sequence: 20,
                    label: _t("Chats"),
                    emptyState: {
                        title: _t("No messages yet!"),
                        subtitle: _t(
                            "Chat with your coworkers on desktop or on mobile.",
                        ),
                    },
                    filters: [
                        {
                            id: "chat_unread",
                            text: _t("Unread"),
                            /** @param {import("models").DiscussChannel} channel */
                            includesChannel: (channel) => channel.isUnread,
                        },
                        {
                            id: "chat_group",
                            text: _t("Group"),
                            /** @param {import("models").DiscussChannel} channel */
                            includesChannel: (channel) =>
                                channel.channel_type === "group",
                        },
                    ],
                    actions,
                };
            },
        });
        this.channelTab = fields.One("MessagingMenuTab", {
            /** @this {import("models").MessagingMenu} */
            compute() {
                const { action } = this.store.env.services;
                return {
                    id: MENU_TABS.CHANNEL,
                    recordType: "discuss.channel",
                    channelTypes: ["channel"],
                    /** @param {import("models").DiscussChannel} channel */
                    includesChannel: (channel) =>
                        Boolean(
                            channel.isLocallyPinned ||
                            channel.self_member_id?.is_pinned ||
                            channel.needactionCounter,
                        ),
                    icon: "fa-solid fa-hashtag",
                    sequence: 40,
                    label: _t("Channels"),
                    emptyState: {
                        title: _t("Stay updated on your favourite topics"),
                        subtitle: _t("Find channels to follow below"),
                        component: MessagingMenuEmptyChannel,
                    },
                    filters: [
                        {
                            id: "channel_unread",
                            text: _t("Unread"),
                            /** @param {import("models").DiscussChannel} channel */
                            includesChannel: (channel) => channel.isUnread,
                        },
                        {
                            id: "channel_thread",
                            text: _t("Thread"),
                            /** @param {import("models").DiscussChannel} channel */
                            includesChannel: (channel) =>
                                Boolean(channel.parent_channel_id),
                        },
                    ],
                    actions:
                        this.store.selfIsInternalUser && action
                            ? [
                                  {
                                      id: "browse_channels",
                                      icon: "fa-solid fa-compass",
                                      title: _t("Browse Channels"),
                                      onClick: () =>
                                          action.doAction(
                                              "mail.discuss_channel_action",
                                          ),
                                  },
                              ]
                            : [],
                };
            },
        });
        this.meetingTab = fields.One("MessagingMenuTab", {
            /** @this {import("models").MessagingMenu} */
            compute() {
                const subActions = [...this.extraTabActions(MENU_TABS.MEETING)];
                if (this.store.selfUser && this.store.startMeeting) {
                    subActions.unshift({
                        id: "start_meeting",
                        text: _t("Start Now"),
                        onClick: () => this.store.startMeeting(),
                    });
                }
                return {
                    id: MENU_TABS.MEETING,
                    recordType: "discuss.channel",
                    channelTypes: ["group"],
                    /** @param {import("models").DiscussChannel} channel */
                    holdsChannel: (channel) => channel.isMeetingOrMeetingChild,
                    /** @param {import("models").DiscussChannel} channel */
                    includesChannel: (channel) =>
                        Boolean(channel.self_member_id?.is_pinned),
                    compareChannels: compareMeetings,
                    icon: "fa-solid fa-video",
                    sequence: 50,
                    label: _t("Meetings"),
                    emptyState: {
                        title: _t("No video conference planned!"),
                        subtitle: _t(
                            "Collaborate with coworkers and customers in video calls. No install needed.",
                        ),
                    },
                    filters: [
                        {
                            id: "meeting_today",
                            text: _t("Today"),
                            /** @param {import("models").DiscussChannel} channel */
                            includesChannel: (channel) => channel.has_meeting_today,
                            isDefault: true,
                            sequence: 10,
                        },
                        {
                            id: "meeting_unread",
                            text: _t("Unread"),
                            /** @param {import("models").DiscussChannel} channel */
                            includesChannel: (channel) => channel.isUnread,
                            compareChannels,
                            sequence: 20,
                        },
                        {
                            id: "meeting_thread",
                            text: _t("Thread"),
                            /** @param {import("models").DiscussChannel} channel */
                            includesChannel: (channel) =>
                                Boolean(channel.parent_channel_id),
                            compareChannels,
                            sequence: 30,
                        },
                        ...this.extraTabFilters(MENU_TABS.MEETING),
                    ],
                    actions: subActions.length
                        ? [
                              {
                                  id: "new_meeting",
                                  icon: "fa-solid fa-video",
                                  text: _t("Meeting"),
                                  title: _t("New Meeting"),
                                  subActions,
                              },
                          ]
                        : [],
                };
            },
        });
    },
    get odooBotNotificationsTab() {
        return this.chatTab;
    },
    /** @param {import("models").Message} message */
    notificationMatchesExtra(message) {
        return (
            super.notificationMatchesExtra(message) &&
            message.thread?.model !== "discuss.channel"
        );
    },
};
patch(MessagingMenu.prototype, messagingMenuPatch);
