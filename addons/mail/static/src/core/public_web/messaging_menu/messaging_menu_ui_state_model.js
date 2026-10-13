// @ts-check
/** @odoo-module native */
import { fields, Record } from "@mail/core/common/record";

export class MessagingMenuUIState extends Record {
    static id = "id";

    /** @type {string} */
    id;
    /** @type {string|undefined} */
    preferredTabId;
    isDisplayed = false;
    selectedTab = fields.One("MessagingMenuTab");
    activeTab = fields.One("MessagingMenuTab", {
        /** @this {import("models").MessagingMenuUIState} */
        compute() {
            const tabs = this.store.messagingMenu?.sortedVisibleTabs ?? [];
            if (this.selectedTab?.canBeShown) {
                return this.selectedTab;
            }
            const preferredTabId = this._preferredTabId();
            return tabs.find((tab) => tab.id === preferredTabId) ?? tabs[0];
        },
        /** @this {import("models").MessagingMenuUIState} */
        onUpdate() {
            const pending = this._pendingFilter;
            this._pendingFilter = undefined;
            this.selectedFilter = pending
                ? pending.filter
                : this.activeTab?.defaultFilter;
            this.pluginFilters = {};
            this.searchTerm = "";
        },
    });
    /** @type {import("models").MessagingMenuTabFilter|undefined} */
    selectedFilter;
    /** @type {{filter: import("models").MessagingMenuTabFilter|undefined}|undefined} */
    _pendingFilter;
    /** @type {Object<string, import("models").MessagingMenuTabFilter>} */
    pluginFilters = {};
    searchTerm = "";
    initialLoadKey = fields.Attr(null, {
        /** @this {import("models").MessagingMenuUIState} */
        compute() {
            if (!this._isReadyForInitialLoad() || !this.activeTab) {
                return null;
            }
            const filterKey = this.activeTab._filterKey(
                this.selectedFilter,
                this.activePluginFilters,
            );
            return `${this.activeTab.id}__${filterKey}`;
        },
        /** @this {import("models").MessagingMenuUIState} */
        onUpdate() {
            if (this.initialLoadKey) {
                this._ensureInitialLoad();
            }
        },
    });

    /** @returns {import("models").MessagingMenuTabFilter[]} */
    get activePluginFilters() {
        return Object.values(this.pluginFilters).filter(Boolean);
    }

    /**
     * @param {string} key
     * @param {import("models").MessagingMenuTabFilter|undefined} filter
     */
    setPluginFilter(key, filter) {
        const others = { ...this.pluginFilters };
        delete others[key];
        this.pluginFilters = filter ? { ...others, [key]: filter } : others;
    }

    /** @param {import("models").MessagingMenuTab} tab */
    selectTab(tab) {
        this.showTab(tab);
    }

    /** @param {import("models").MessagingMenuTabFilter} [filter] */
    selectFilter(filter) {
        this.selectedFilter = filter;
    }

    /**
     * @param {import("models").MessagingMenuTab} tab
     * @param {{filter?: import("models").MessagingMenuTabFilter}} [options]
     */
    showTab(tab, options) {
        if (this.activeTab?.eq(tab)) {
            if (options && "filter" in options) {
                this.selectedFilter = options.filter;
            }
            return;
        }
        this._pendingFilter =
            options && "filter" in options ? { filter: options.filter } : undefined;
        this.selectedTab = tab;
    }

    /** @returns {string|undefined} */
    _preferredTabId() {
        return this.preferredTabId;
    }

    /** @returns {boolean} */
    _isReadyForInitialLoad() {
        return this.isDisplayed;
    }

    _ensureInitialLoad() {
        const tab = this.activeTab;
        if (
            tab?.getLoadStatus(this.selectedFilter, this.activePluginFilters) === "new"
        ) {
            tab.loadMore({
                filter: this.selectedFilter,
                pluginFilters: this.activePluginFilters,
            });
        }
    }
}

MessagingMenuUIState.register();
