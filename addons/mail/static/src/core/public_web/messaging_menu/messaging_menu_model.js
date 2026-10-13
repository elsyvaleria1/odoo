// @ts-check
/** @odoo-module native */
import { fields, Record } from "@mail/core/common/record";

/** @type {import("menu_tabs").MenuTabs} */
export const MENU_TABS = {};

export class MessagingMenu extends Record {
    allTabs = fields.Many("MessagingMenuTab", {
        /** @this {import("models").MessagingMenu} */
        compute() {
            return Object.values(this.store.MessagingMenuTab.records);
        },
        /** @this {import("models").MessagingMenu} */
        onAdd(tab) {
            if (this.initializeCountersFetcher.status !== "not_fetched") {
                this._fetchCounters([tab]);
            }
        },
    });
    visibleTabs = fields.Many("MessagingMenuTab", {
        /** @this {import("models").MessagingMenu} */
        compute() {
            return this.allTabs.filter((tab) => tab.appWide && tab.canBeShown);
        },
        sort: (t1, t2) => t1.sequence - t2.sequence || t1.id.localeCompare(t2.id),
    });
    /** @type {ReturnType<import("models").Store["makeCachedFetchData"]>|undefined} */
    _initializeCountersFetcher;

    get initializeCountersFetcher() {
        this._initializeCountersFetcher ??= this.store.makeCachedFetchData(
            "/mail/messaging_menu/initialize_counters",
            () => this._counterRequest(this.allTabs),
        );
        return this._initializeCountersFetcher;
    }

    /** @param {import("models").MessagingMenuTab[]} tabs */
    _fetchCounters(tabs) {
        const request = this._counterRequest(tabs);
        if (Object.keys(request.filter_id_by_tab_id_by_record_type).length) {
            this.store.fetchStoreData(
                "/mail/messaging_menu/initialize_counters",
                request,
            );
        }
    }

    /** @returns {Readonly<import("models").MessagingMenuTab[]>} */
    get sortedVisibleTabs() {
        return this.visibleTabs;
    }

    /**
     * @param {Readonly<import("models").MessagingMenuTab[]>} tabs
     * @returns {{
     *   filter_id_by_tab_id_by_record_type: Object<string, Object<string, string|null>>,
     *   presence_tab_ids: string[],
     * }}
     */
    _counterRequest(tabs) {
        /** @type {Object<string, Object<string, string|null>>} */
        const filterIdByTabIdByRecordType = {};
        /** @type {string[]} */
        const presenceTabIds = [];
        for (const tab of tabs.filter((tab) => !tab.storeCounter)) {
            filterIdByTabIdByRecordType[tab.recordType] ??= {};
            filterIdByTabIdByRecordType[tab.recordType][tab.id] =
                tab.defaultFilter?.id ?? null;
            if (tab.hideWhenEmpty) {
                presenceTabIds.push(tab.id);
            }
        }
        return {
            filter_id_by_tab_id_by_record_type: filterIdByTabIdByRecordType,
            presence_tab_ids: presenceTabIds,
        };
    }

    /**
     * @param {import("models").Message} message
     * @returns {boolean}
     */
    notificationMatchesExtra(message) {
        return true;
    }

    /**
     * @param {string} tabId
     * @returns {import("@mail/core/public_web/messaging_menu/messaging_menu_tab_model").MessagingMenuTabAction[]}
     */
    extraTabActions(tabId) {
        return [];
    }

    /**
     * @param {string} tabId
     * @returns {import("models").MessagingMenuTabFilter[]}
     */
    extraTabFilters(tabId) {
        return [];
    }

    /** @returns {import("models").MessagingMenuTab|undefined} */
    get odooBotNotificationsTab() {
        return undefined;
    }
}

MessagingMenu.register();
