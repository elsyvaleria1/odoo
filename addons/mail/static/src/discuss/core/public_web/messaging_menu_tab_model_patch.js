// @ts-check
/** @odoo-module native */
import { threadCompareRegistry } from "@mail/core/common/thread_compare";
import { MessagingMenuTab } from "@mail/core/public_web/messaging_menu/messaging_menu_tab_model";
import { fields } from "@mail/model/misc";
import { patch } from "@web/core/utils/patch";

/**
 * @param {import("models").Thread} thread1
 * @param {import("models").Thread} thread2
 */
export function compareChannels(thread1, thread2) {
    for (const fn of threadCompareRegistry.getAll()) {
        const result = fn(thread1, thread2);
        if (result !== undefined) {
            return result;
        }
    }
    return thread2.localId > thread1.localId ? 1 : -1;
}

/** @type {Partial<import("models").MessagingMenuTab> & ThisType<import("models").MessagingMenuTab>} */
const messagingMenuTabPatch = {
    setup() {
        super.setup();
        this.channels = fields.Many("discuss.channel", {
            inverse: "messagingMenuTabs",
        });
        this.channelsWithCounter = fields.Many("discuss.channel", {
            inverse: "messagingMenuTabsWithCounter",
        });
        this.counterChannelsToResolve = fields.Many("discuss.channel", {
            /** @this {import("models").MessagingMenuTab} */
            compute() {
                return this.init_counter_ids
                    .map((id) => this.store["discuss.channel"].get(id))
                    .filter(Boolean);
            },
            /** @this {import("models").MessagingMenuTab} */
            onAdd(channel) {
                this._resolveCounterChannel(channel);
            },
        });
        /** @type {string[]} */
        this.channelTypes = [];
        /** @type {(channel: import("models").DiscussChannel) => boolean} */
        this.holdsChannel = () => true;
        /** @type {(channel: import("models").DiscussChannel) => boolean} */
        this.includesChannel = () => false;
        /**
         * @type {((c1: import("models").DiscussChannel, c2: import("models").DiscussChannel) => number)|undefined}
         */
        this.compareChannels = undefined;
    },
    /** @param {import("models").DiscussChannel} channel */
    async _resolveCounterChannel(channel) {
        const id = Number(channel.id);
        const resolved = (
            await this.store.Thread.getOrFetch({ model: "discuss.channel", id })
        )?.channel;
        if (resolved?.fetchChannelInfoState === "fetched" || !resolved?.exists()) {
            this.init_counter_ids = this.init_counter_ids.filter(
                (counterId) => counterId !== id,
            );
        }
    },
    get hasContent() {
        return (
            super.hasContent ||
            (this.recordType === "discuss.channel" && this.channels.length > 0)
        );
    },
    /**
     * @param {import("models").MessagingMenuTabFilter[]} [filters]
     * @returns {import("models").DiscussChannel[]}
     */
    getSortedChannels(filters = []) {
        const compare =
            filters.findLast((f) => f.compareChannels)?.compareChannels ??
            this.compareChannels ??
            compareChannels;
        return this.channels
            .filter((channel) =>
                filters.every((f) => !f.includesChannel || f.includesChannel(channel)),
            )
            .sort(compare);
    },
    /** @param {import("models").DiscussChannel} channel */
    hasChannelKind(channel) {
        return (
            this.channelTypes.includes(channel.channel_type) &&
            this.holdsChannel(channel)
        );
    },
    _computeCounter() {
        if (this.recordType !== "discuss.channel") {
            return super._computeCounter();
        }
        const unloaded = this.init_counter_ids.filter(
            (id) =>
                this.store["discuss.channel"].get(id)?.fetchChannelInfoState !==
                "fetched",
        );
        return this.channelsWithCounter.length + unloaded.length + this.extraCounter;
    },
    get loadMoreExcludeIds() {
        if (this.recordType !== "discuss.channel") {
            return super.loadMoreExcludeIds;
        }
        return this.channels
            .filter(
                (channel) =>
                    channel.last_message_fetched ||
                    channel.isLoaded ||
                    channel.eq(this.store.discuss?.thread),
            )
            .map((channel) => Number(channel.id));
    },
};
patch(MessagingMenuTab.prototype, messagingMenuTabPatch);
