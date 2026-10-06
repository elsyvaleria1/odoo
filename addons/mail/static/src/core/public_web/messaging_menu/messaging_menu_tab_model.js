// @ts-check
/** @odoo-module native */
import { fields, Record } from "@mail/core/common/record";
import { compareDatetime } from "@mail/utils/common/misc";
import { _t } from "@web/core/translation";

/**
 * @typedef {import("models").MessagingMenuTabFilter} MessagingMenuTabFilter
 * @typedef {"new"|"idle"|"loading"|"loaded"} MessagingMenuTabLoadStatus
 * @typedef {{
 *   id: string,
 *   text?: string,
 *   icon?: string,
 *   title?: string,
 *   isDisabled?: () => boolean,
 *   onClick?: () => void,
 *   preventDropdownClose?: boolean,
 *   subActions?: MessagingMenuTabAction[],
 * }} MessagingMenuTabAction
 */

export class MessagingMenuTab extends Record {
    static id = "id";
    static LOAD_MORE_LIMIT = 20;

    /** @type {string} */
    id;
    /** @type {"mail.message"|"discuss.channel"} */
    recordType;
    /** @type {string} */
    label;
    /** @type {string} */
    icon;
    sequence = 0;
    appWide = true;
    important = true;
    hideWhenZeroCounter = false;
    hideWhenEmpty = false;
    has_records = false;
    /** @type {MessagingMenuTabAction[]} */
    actions = [];
    /** @type {MessagingMenuTabFilter[]} */
    filters = [];
    /**
     * @type {{
     *   title?: string,
     *   subtitle?: string,
     *   component?: typeof import("@odoo/owl").Component,
     * }}
     */
    emptyState = { title: _t("Nothing here yet.") };
    /** @type {(message: import("models").Message) => boolean} */
    includesMessage = () => false;
    /** @type {string[]|undefined} the message actions its items offer */
    messageActionIds;
    /** @type {number[]} */
    init_counter_ids = [];
    /** @type {Object<string, MessagingMenuTabLoadStatus>} */
    loadStatusByFilterId = {};
    messages = fields.Many("mail.message", { inverse: "messagingMenuTabsAsMessages" });
    /** @type {"needaction_counter"|"starred_counter"|undefined} the store counter this tab presents */
    storeCounter;
    counter = fields.Attr(0, {
        /** @this {import("models").MessagingMenuTab} */
        compute() {
            return this._computeCounter();
        },
    });
    extraCounter = fields.Attr(0, {
        /** @this {import("models").MessagingMenuTab} */
        compute() {
            if (!this.eq(this.store.messagingMenu?.odooBotNotificationsTab)) {
                return 0;
            }
            return this.store.failures.reduce(
                (count, failure) => count + failure.notifications.length,
                0,
            );
        },
    });

    get sortedMessages() {
        return [...this.messages].sort(
            (m1, m2) =>
                compareDatetime(m2.create_date, m1.create_date) ||
                Number(m2.id) - Number(m1.id),
        );
    }

    get sortedFilters() {
        return [...this.filters].sort(
            (f1, f2) => (f1.sequence ?? 0) - (f2.sequence ?? 0),
        );
    }

    get defaultFilter() {
        return this.filters.find((filter) => filter.isDefault);
    }

    get canBeShown() {
        return (
            (!this.hideWhenZeroCounter || this.counter > 0) &&
            (!this.hideWhenEmpty || this.hasContent)
        );
    }

    get hasContent() {
        return this.has_records || this.counter > 0 || this.messages.length > 0;
    }

    /** @returns {number[]} */
    get loadMoreExcludeIds() {
        return this.messages.map((message) => Number(message.id));
    }

    /** @returns {number} */
    _computeCounter() {
        if (this.storeCounter) {
            return (this.store[this.storeCounter] ?? 0) + this.extraCounter;
        }
        const defaultFilter = this.defaultFilter;
        /** @param {import("models").Message} message */
        const isCountable = (message) =>
            !defaultFilter?.includesMessage || defaultFilter.includesMessage(message);
        const countable = this.messages.filter(isCountable);
        const countedIds = new Set(countable.map((message) => Number(message.id)));
        const unloaded = this.init_counter_ids.filter((id) => {
            if (countedIds.has(id)) {
                return false;
            }
            const message = this.store["mail.message"].get(id);
            return !message || (this.includesMessage(message) && isCountable(message));
        });
        return countable.length + unloaded.length + this.extraCounter;
    }

    /**
     * @param {MessagingMenuTabFilter} [filter]
     * @param {MessagingMenuTabFilter[]} [pluginFilters]
     * @returns {string}
     */
    _filterKey(filter, pluginFilters = []) {
        const ids = [filter?.id, ...pluginFilters.map((f) => f.id)]
            .filter(Boolean)
            .sort();
        return ids.length ? ids.join("__") : "_base";
    }

    /**
     * A search loads its own pages: its status must neither wait on nor end
     * the browsing of the same filters.
     *
     * @param {MessagingMenuTabFilter} [filter]
     * @param {MessagingMenuTabFilter[]} [pluginFilters]
     * @param {string} [searchTerm]
     * @returns {string}
     */
    _loadKey(filter, pluginFilters = [], searchTerm = "") {
        const filterKey = this._filterKey(filter, pluginFilters);
        const term = searchTerm.trim().toLowerCase();
        return term ? `${filterKey}::${term}` : filterKey;
    }

    /**
     * @param {MessagingMenuTabFilter} [filter]
     * @param {MessagingMenuTabFilter[]} [pluginFilters]
     * @param {string} [searchTerm]
     * @returns {MessagingMenuTabLoadStatus}
     */
    getLoadStatus(filter, pluginFilters = [], searchTerm = "") {
        if (this.loadStatusByFilterId._base === "loaded") {
            return "loaded";
        }
        const filterKey = this._filterKey(filter, pluginFilters);
        const key = this._loadKey(filter, pluginFilters, searchTerm);
        if (key === filterKey || this.loadStatusByFilterId[filterKey] === "loaded") {
            return this.loadStatusByFilterId[filterKey] ?? "new";
        }
        // the server matches a term as a substring: every match of a term
        // containing a fully loaded one is already here
        const termPrefix = `${filterKey}::`;
        const term = key.slice(termPrefix.length);
        const covered = Object.entries(this.loadStatusByFilterId).some(
            ([loadedKey, status]) =>
                status === "loaded" &&
                loadedKey.startsWith(termPrefix) &&
                term.includes(loadedKey.slice(termPrefix.length)),
        );
        return covered ? "loaded" : (this.loadStatusByFilterId[key] ?? "new");
    }

    /**
     * @param {string} key
     * @param {MessagingMenuTabLoadStatus} status
     */
    _setLoadStatus(key, status) {
        this.loadStatusByFilterId = { ...this.loadStatusByFilterId, [key]: status };
    }

    markStale() {
        this.loadStatusByFilterId = {};
    }

    /**
     * @param {Object} [options]
     * @param {MessagingMenuTabFilter} [options.filter]
     * @param {MessagingMenuTabFilter[]} [options.pluginFilters]
     * @param {string} [options.searchTerm]
     */
    async loadMore({ filter, pluginFilters = [], searchTerm = "" } = {}) {
        if (
            !["new", "idle"].includes(
                this.getLoadStatus(filter, pluginFilters, searchTerm),
            )
        ) {
            return;
        }
        const key = this._loadKey(filter, pluginFilters, searchTerm);
        this._setLoadStatus(key, "loading");
        try {
            const result = await this.store.fetchStoreData(
                `/mail/messaging_menu/${this.recordType}/load_more`,
                {
                    tab_id: this.id,
                    filter_ids: [filter?.id, ...pluginFilters.map((f) => f.id)].filter(
                        Boolean,
                    ),
                    exclude_ids: this.loadMoreExcludeIds,
                    limit: MessagingMenuTab.LOAD_MORE_LIMIT,
                    search_term: searchTerm || undefined,
                },
                { requestData: true },
            );
            this._setLoadStatus(key, result?.is_fully_loaded ? "loaded" : "idle");
        } finally {
            if (this.loadStatusByFilterId[key] === "loading") {
                this._setLoadStatus(key, "idle");
            }
        }
    }
}

MessagingMenuTab.register();
