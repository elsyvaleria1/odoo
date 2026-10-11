// @ts-check
/** @odoo-module native */
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { fields } from "@mail/model/misc";
import { compareDatetime } from "@mail/utils/common/misc";
import { makeLogger } from "@web/core/debug/debug_logger";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

const log = makeLogger("mail.thread");
/** @type {Partial<import("models").DiscussChannel> & ThisType<import("models").DiscussChannel>} */
const threadPatch = {
    setup() {
        super.setup();
        this.from_message_id = fields.One("mail.message");
        this.last_message_fetched = false;
        this.messagingMenuTabs = fields.Many("MessagingMenuTab", {
            inverse: "channels",
            /** @this {import("models").DiscussChannel} */
            compute() {
                return (this.store.messagingMenu?.allTabs ?? []).filter(
                    (tab) => tab.hasChannelKind(this) && tab.includesChannel(this),
                );
            },
        });
        this.messagingMenuTabsWithCounter = fields.Many("MessagingMenuTab", {
            inverse: "channelsWithCounter",
            /** @this {import("models").DiscussChannel} */
            compute() {
                return this._computeMessagingMenuTabsWithCounter();
            },
        });
        this.parent_channel_id = fields.One("discuss.channel", {
            /** @this {import("models").DiscussChannel} */
            onDelete() {
                this.delete();
            },
        });
        this.sub_channel_ids = fields.Many("discuss.channel", {
            inverse: "parent_channel_id",
            sort: (a, b) =>
                compareDatetime(b.lastInterestDt, a.lastInterestDt) ||
                Number(b.id) - Number(a.id),
        });
        this.loadSubChannelsDone = false;
        /** @type {import("models").Thread|null} */
        this.lastSubChannelLoaded = null;
        this.searchSubChannelsDone = false;
        /** @type {import("models").Thread|null} */
        this.lastSearchSubChannelLoaded = null;
        this.subChannelSearchTerm = "";
    },
    /** @returns {import("models").MessagingMenuTab[]} */
    _computeMessagingMenuTabsWithCounter() {
        const member = this.self_member_id;
        const hasUnread =
            member?.is_pinned && !member.mute_until_dt && member.message_unread_counter;
        if (!hasUnread && !this.message_needaction_counter) {
            return [];
        }
        return this.messagingMenuTabs.filter(
            (tab) => !tab.defaultFilter || tab.defaultFilter.includesChannel?.(this),
        );
    },
    async joinAndPin() {
        if (this.self_member_id) {
            await this.store.env.services.orm.silent.call(
                "discuss.channel",
                "channel_pin",
                [this.id],
                { pinned: true },
            );
            return;
        }
        this.store.insert(await rpc("/discuss/channel/join", { channel_id: this.id }));
    },
    get canLeave() {
        return !this.parent_channel_id && super.canLeave;
    },
    /** @returns {import("models").MessagingMenuTab|undefined} */
    get primaryMessagingMenuTab() {
        return this.messagingMenuTabs.find((tab) => tab.appWide);
    },
    /** @returns {import("models").MessagingMenuTab|undefined} */
    get typeMessagingMenuTab() {
        return (
            this.primaryMessagingMenuTab ??
            this.store.messagingMenu?.allTabs.find(
                (tab) => tab.appWide && tab.hasChannelKind(this),
            )
        );
    },
    /** @param {import("models").MessagingMenuUIState} state */
    revealInMessagingMenu(state) {
        super.revealInMessagingMenu(state);
        if (state.activeTab?.recordType === "mail.message") {
            return;
        }
        if (this.primaryMessagingMenuTab) {
            state.showTab(this.primaryMessagingMenuTab);
        }
    },
    get canUnpin() {
        return Boolean(this.parent_channel_id) || super.canUnpin;
    },
    get fullNameWithParent() {
        if (this.parent_channel_id) {
            return `${this.parent_channel_id.displayName} > ${this.displayName}`;
        }
        return super.fullNameWithParent;
    },
    get composerPlaceholder() {
        if (this.typePolicy.describes_as_channel && this.parent_channel_id) {
            return _t('Message "%(subChannelName)s"', {
                subChannelName: this.displayName,
            });
        }
        return super.composerPlaceholder;
    },
    get conversationStartTitle() {
        if (this.parent_channel_id) {
            return this.name;
        }
        return super.conversationStartTitle;
    },
    get conversationStartSubtitle() {
        if (this.parent_channel_id) {
            const authorName = Object.values(this.store["res.partner"].records).find(
                (partner) => partner.main_user_id?.eq(this.create_uid),
            )?.name;
            if (authorName) {
                return _t("Started by %(authorName)s", { authorName });
            }
        }
        return super.conversationStartSubtitle;
    },
    get allowCalls() {
        return super.allowCalls && !this.parent_channel_id;
    },
    get hasSubChannelFeature() {
        return Boolean(this.typePolicy.supports_sub_channels);
    },
    get isEmpty() {
        return !this.from_message_id && super.isEmpty;
    },
    /**
     * @param {Object} [param0={}]
     * @param {import("models").Message} [param0.initialMessage]
     * @param {string} [param0.name]
     */
    async createSubChannel({ initialMessage, name } = {}) {
        log.logic("createSubChannel", () => ({
            parent: this.parent_channel_id?.id || this.id,
            fromMessageId: initialMessage?.id,
            named: Boolean(name),
        }));
        const { store_data, sub_channel } = await rpc(
            "/discuss/channel/sub_channel/create",
            {
                parent_channel_id: this.parent_channel_id?.id || this.id,
                from_message_id: initialMessage?.id,
                name,
            },
        );
        this.store.insert(store_data);
        this.store["discuss.channel"].get(sub_channel).open({
            focus: true,
        });
    },
    /**
     * @param {Object} [param0={}]
     * @param {string} [param0.searchTerm]
     * @returns {Promise<import("models").Thread[]|undefined>}
     */
    async loadMoreSubChannels({ searchTerm } = {}) {
        if (searchTerm && searchTerm !== this.subChannelSearchTerm) {
            this.subChannelSearchTerm = searchTerm;
            this.lastSearchSubChannelLoaded = null;
            this.searchSubChannelsDone = false;
        }
        if (searchTerm ? this.searchSubChannelsDone : this.loadSubChannelsDone) {
            log.logic("loadMoreSubChannels exhausted", () => ({
                thread: this.localId,
                searchTerm,
            }));
            return;
        }
        const limit = 30;
        const endLoad = log.perf("loadMoreSubChannels");
        const { store_data, sub_channel_ids } = await rpc(
            "/discuss/channel/sub_channel/fetch",
            {
                before: searchTerm
                    ? this.lastSearchSubChannelLoaded?.id
                    : this.lastSubChannelLoaded?.id,
                limit,
                parent_channel_id: this.id,
                search_term: searchTerm,
            },
        );
        this.store.insert(store_data);
        endLoad({
            thread: this.localId,
            searchTerm,
            fetched: sub_channel_ids.length,
            limit,
        });
        const threads = sub_channel_ids.map((subChannelId) =>
            this.store["discuss.channel"].get(subChannelId),
        );

        const subChannels = threads.filter((thread) =>
            this.eq(thread.parent_channel_id),
        );
        if (searchTerm) {
            this.lastSearchSubChannelLoaded = subChannels.reduce(
                (min, channel) => (!min || channel.id < min.id ? channel : min),
                this.lastSearchSubChannelLoaded,
            );
            if (sub_channel_ids.length < limit) {
                this.searchSubChannelsDone = true;
            }
            return;
        }
        this.lastSubChannelLoaded = subChannels.reduce(
            (min, channel) => (!min || channel.id < min.id ? channel : min),
            this.lastSubChannelLoaded,
        );
        if (subChannels.length < limit) {
            this.loadSubChannelsDone = true;
        }
        return subChannels;
    },
    onPinStateUpdated() {
        super.onPinStateUpdated();
        if (this.self_member_id?.is_pinned) {
            this.isLocallyPinned = false;
        }
        if (!this.self_member_id?.is_pinned && !this.isLocallyPinned) {
            this.sub_channel_ids.forEach((c) => (c.isLocallyPinned = false));
        }
    },
    openChannel() {
        if (this.store.discuss.isActive && !this.store.env.services.ui.isSmall) {
            log.logic("openChannel in discuss", () => ({ thread: this.localId }));
            this.setAsDiscussThread();
            return true;
        }
        return super.openChannel();
    },
    setAsDiscussThread() {
        if (!this.displayToSelf && this.isChannelKind) {
            this.isLocallyPinned = true;
        }
        super.setAsDiscussThread(...arguments);
    },
};
patch(DiscussChannel.prototype, threadPatch);
