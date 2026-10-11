/** @odoo-module native */
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { MessagingMenuTab } from "@mail/core/public_web/messaging_menu/messaging_menu_tab_model";
import { fields } from "@mail/model/misc";
import { effectWithDebouncedCleanup } from "@mail/utils/common/misc";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.LIVECHAT = "livechat";

export const LFH_UNSUBSCRIBE_DELAY = 5 * 60 * 1000;
export const LIVECHAT_CHANNEL_FILTER_PREFIX = "livechat_channel_";

patch(MessagingMenu, {
    new() {
        /** @type {import("models").MessagingMenu} */
        const menu = super.new(...arguments);
        effectWithDebouncedCleanup({
            delay: LFH_UNSUBSCRIBE_DELAY,
            dependencies: (menu) => ({
                busService: menu.store.env.services.bus_service,
                store: menu.store,
            }),
            effect({ busService, store }) {
                const releaseChannel = busService.addChannel(
                    "im_livechat.looking_for_help",
                );
                store.fetchStoreData("/im_livechat/looking_for_help");
                return () => {
                    releaseChannel();
                    Object.values(store["discuss.channel"].records)
                        .filter(
                            (channel) =>
                                channel.livechat_status === "need_help" &&
                                !channel.self_member_id &&
                                !channel.isLocallyPinned,
                        )
                        .forEach((channel) => channel.delete());
                };
            },
            predicate: (menu) =>
                Boolean(
                    menu.exists() &&
                    menu.store.has_access_livechat &&
                    menu.isLivechatTabDisplayed,
                ),
            reactiveTargets: [menu],
        });
        return menu;
    },
});

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        this.livechatTab = fields.One("MessagingMenuTab", {
            compute() {
                return {
                    id: MENU_TABS.LIVECHAT,
                    recordType: "discuss.channel",
                    channelTypes: ["livechat"],
                    includesChannel: (channel) =>
                        Boolean(
                            channel.self_member_id?.is_pinned ||
                            channel.isLocallyPinned ||
                            channel.livechat_status === "need_help",
                        ),
                    icon: "fa-regular fa-comment-dots",
                    sequence: 60,
                    label: _t("Live Chats"),
                    hideWhenEmpty: true,
                    emptyState: {
                        title: _t("No Livechat Session!"),
                        subtitle: _t(
                            "Engage with visitors to convert leads or offer services.",
                        ),
                    },
                    filters: [
                        {
                            id: "livechat_unread",
                            text: _t("Unread"),
                            includesChannel: (channel) => channel.isUnread,
                        },
                        ...(this.store.has_access_livechat
                            ? [
                                  {
                                      id: "livechat_need_help",
                                      text: _t("Help needed"),
                                      includesChannel: (channel) =>
                                          channel.livechat_status === "need_help",
                                  },
                              ]
                            : []),
                    ],
                };
            },
        });
        this.isLivechatTabDisplayed = fields.Attr(false, {
            compute() {
                return Object.values(this.store.MessagingMenuUIState.records).some(
                    (state) =>
                        state.isDisplayed && state.activeTab?.eq(this.livechatTab),
                );
            },
        });
    },
    /** @returns {import("models").MessagingMenuTabFilter[]} */
    get livechatChannelFilters() {
        return Object.values(this.store["im_livechat.channel"].records)
            .filter((livechatChannel) => livechatChannel.are_you_inside)
            .sort(
                (c1, c2) =>
                    (c1.name ?? "").localeCompare(c2.name ?? "") || c1.id - c2.id,
            )
            .map((livechatChannel) => ({
                id: `${LIVECHAT_CHANNEL_FILTER_PREFIX}${livechatChannel.id}`,
                text: livechatChannel.name,
                includesChannel: (channel) =>
                    Boolean(channel.livechat_channel_id?.eq(livechatChannel)),
            }));
    },
});

patch(MessagingMenuTab.prototype, {
    get hasContent() {
        return (
            (this.id === MENU_TABS.LIVECHAT &&
                Boolean(this.store.has_access_livechat)) ||
            super.hasContent
        );
    },
});
