// @ts-check
/** @odoo-module native */
import { ImStatus } from "@mail/core/common/im_status";
import { IsolatedDropdown } from "@mail/core/public_web/messaging_menu/isolated_dropdown";
import { MessageInDialog } from "@mail/core/public_web/messaging_menu/message_in_dialog";
import { MessagingMenuEmpty } from "@mail/core/public_web/messaging_menu/messaging_menu_empty";
import { MessagingMenuItem } from "@mail/core/public_web/messaging_menu/messaging_menu_item";
import { NotificationItem } from "@mail/core/public_web/notification_item";
import { cleanTerm, htmlToTextContentInline } from "@mail/utils/common/format";
import { useOnBottomScrolled } from "@mail/utils/common/hooks";
import { provideMailContext } from "@mail/utils/common/mail_context";
import { navigateIndex } from "@mail/utils/common/misc";
import { Component, onMounted, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import {
    hasTouch,
    isDisplayStandalone,
    isIOS,
} from "@web/core/browser/feature_detection";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useMountedListener, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useDebounced } from "@web/core/utils/timing";

const log = makeLogger("mail.messaging_menu");

/** @typedef {import("@mail/core/public_web/messaging_menu/messaging_menu_tab_model").MessagingMenuTabAction} MessagingMenuTabAction */
/**
 * @typedef {{
 *   key: string,
 *   text: string,
 *   filters: import("models").MessagingMenuTabFilter[],
 * }} MessagingMenuPluginFilterGroup
 */

export const PLUGIN_FILTER_CHIP_LIMIT = 3;

export const messagingMenuProps = {
    state: t.any(),
    close: t.any().optional(),
    collapsed: t.boolean().optional(false),
    onToggleCollapsed: t.any().optional(),
};

export class MessagingMenu extends Component {
    static components = {
        Dropdown,
        IsolatedDropdown,
        DropdownItem,
        ImStatus,
        MessagingMenuEmpty,
        MessagingMenuItem,
        NotificationItem,
    };
    static props = messagingMenuProps;
    static template = "mail.MessagingMenu";
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        super.setup();
        this.isIosPwa = isIOS() && isDisplayStandalone();
        this.hasTouch = hasTouch;
        this.store = useService("mail.store");
        this.ui = useService("ui");
        this.dialog = useService("dialog");
        this.notification = useService("mail.notification.permission");
        this.rootRef = elementRef();
        this.listRef = elementRef();
        this.searchInputRef = elementRef();
        this.local = proxy({
            /** @type {number|null} */
            activeIndex: null,
        });
        provideMailContext({ inMessagingMenu: { close: () => this.close() } });
        onMounted(() => {
            this.state.isDisplayed = true;
            this.store.messagingMenu.initializeCountersFetcher.fetch();
        });
        onWillUnmount(() => {
            this.state.isDisplayed = false;
        });
        useLayoutEffect(
            () => {
                this.local.activeIndex = null;
            },
            () => [this.state.activeTab, this.state.selectedFilter],
        );
        useLayoutEffect(
            /** @param {string} searchTerm */
            (searchTerm) => {
                if (!searchTerm) {
                    this.local.activeIndex = null;
                } else if (this.local.activeIndex !== null) {
                    this.local.activeIndex = 0;
                }
            },
            () => [this.state.searchTerm],
        );
        this.searchServer = useDebounced(
            /**
             * @param {import("models").MessagingMenuTab} tab
             * @param {string} searchTerm
             */
            (tab, searchTerm) =>
                tab.loadMore({
                    filter: this.state.selectedFilter,
                    pluginFilters: this.state.activePluginFilters,
                    searchTerm,
                }),
            300,
        );
        useLayoutEffect(
            /**
             * @param {import("models").MessagingMenuTab|undefined} tab
             * @param {string} searchTerm
             * @param {string|undefined} loadStatus
             */
            (tab, searchTerm, loadStatus) => {
                if (tab && searchTerm && loadStatus === "new") {
                    this.searchServer(tab, searchTerm);
                }
            },
            () => [this.activeTab, this.state.searchTerm, this.loadStatus],
        );
        useOnBottomScrolled(this.listRef, () => this.loadMore());
        useLayoutEffect(
            () => this.fillList(),
            () => [this.itemCount, this.loadStatus],
        );
        useLayoutEffect(
            /** @param {HTMLElement|null} list */
            (list) => {
                if (!list) {
                    return;
                }
                const observer = new ResizeObserver(() => this.fillList());
                observer.observe(list);
                return () => observer.disconnect();
            },
            () => [this.listRef.el],
        );
        useMountedListener(window, "keydown", this.onKeydown.bind(this), true);
    }

    /** @returns {import("models").MessagingMenuUIState} */
    get state() {
        return this.props.state;
    }

    /** @returns {import("models").MessagingMenuTab|undefined} */
    get activeTab() {
        return this.state.activeTab;
    }

    get visibleTabs() {
        return this.store.messagingMenu.sortedVisibleTabs;
    }

    close() {
        this.props.close?.();
    }

    fillList() {
        const list = this.listRef.el;
        if (
            list &&
            this.loadStatus === "idle" &&
            list.scrollHeight <= list.clientHeight
        ) {
            this.loadMore();
        }
    }

    loadMore() {
        this.activeTab?.loadMore({
            filter: this.state.selectedFilter,
            pluginFilters: this.state.activePluginFilters,
            searchTerm: this.state.searchTerm,
        });
    }

    /** @returns {import("models").MessagingMenuTabFilter[]} */
    get activeFilters() {
        const filters = [...this.state.activePluginFilters];
        if (this.state.selectedFilter) {
            filters.push(this.state.selectedFilter);
        }
        return filters;
    }

    /** @returns {import("models").Message[]} */
    get messages() {
        const tab = this.activeTab;
        if (!tab || tab.recordType !== "mail.message") {
            return [];
        }
        const filters = this.activeFilters;
        const searchTerm = cleanTerm(this.state.searchTerm);
        return tab.sortedMessages.filter(
            (message) =>
                filters.every(
                    (f) => !f.includesMessage || f.includesMessage(message),
                ) &&
                (!searchTerm ||
                    [
                        message.thread?.displayName,
                        message.authorName,
                        htmlToTextContentInline(message.previewText),
                    ].some((text) => cleanTerm(text ?? "").includes(searchTerm))),
        );
    }

    get itemCount() {
        return this.messages.length;
    }

    get isEmpty() {
        return !this.itemCount && !this.prefixItems.length;
    }

    /** @returns {import("@mail/core/public_web/messaging_menu/messaging_menu_tab_model").MessagingMenuTabLoadStatus|undefined} */
    get loadStatus() {
        return this.activeTab?.getLoadStatus(
            this.state.selectedFilter,
            this.state.activePluginFilters,
            this.state.searchTerm,
        );
    }

    get isLoading() {
        return (
            this.loadStatus === "loading" ||
            (Boolean(this.state.searchTerm) && this.loadStatus === "new")
        );
    }

    get isFullyLoaded() {
        return this.loadStatus === "loaded";
    }

    get collapseTitle() {
        return _t("Collapse to the tabs");
    }

    get expandTitle() {
        return _t("Expand the conversation list");
    }

    get searchPlaceholder() {
        return this.activeTab ? _t("Search %s", this.activeTab.label) : _t("Search");
    }

    get noSearchResultText() {
        return this.state.searchTerm
            ? _t('No results for "%s".', this.state.searchTerm)
            : "";
    }

    get noFilterResultText() {
        return _t("No conversation matches this filter.");
    }

    get showFilterEmptyState() {
        const filter = this.state.selectedFilter;
        return Boolean(
            (filter && !filter.isDefault) || this.state.activePluginFilters.length,
        );
    }

    get showNotificationHubExtras() {
        return Boolean(
            !this.state.searchTerm &&
            !this.state.selectedFilter &&
            this.activeTab &&
            this.activeTab.eq(this.store.messagingMenu.odooBotNotificationsTab),
        );
    }

    get shouldAskPushPermission() {
        return (
            this.notification.permission === "prompt" &&
            !this.store.isNotificationPermissionDismissed
        );
    }

    get showPushPermissionRequest() {
        return this.shouldAskPushPermission && this.showNotificationHubExtras;
    }

    get notificationRequest() {
        return {
            body: _t("Stay tuned! Enable push notifications to never miss a message."),
            displayName: _t("Turn on notifications"),
            iconSrc: this.store.odoobot?.avatarUrl,
            partner: this.store.odoobot,
        };
    }

    /**
     * Keys of the items listed before the tab's own items, in display order: an
     * item's keyboard index is its position here.
     *
     * @returns {string[]}
     */
    get prefixItems() {
        return this.showPushPermissionRequest ? ["notificationRequest"] : [];
    }

    /** @param {string} key */
    isPrefixItemActive(key) {
        return this.local.activeIndex === this.prefixItems.indexOf(key);
    }

    /** @param {number} index position among the tab's own items */
    isItemActive(index) {
        return this.local.activeIndex === this.prefixItems.length + index;
    }

    /** @param {import("models").MessagingMenuTab} tab */
    getTabCounter(tab) {
        return tab.counter + this.getTabExtraCounter(tab);
    }

    /**
     * Requests shown in a tab that are not records, so its model cannot count them.
     *
     * @param {import("models").MessagingMenuTab} tab
     */
    getTabExtraCounter(tab) {
        if (!tab.eq(this.store.messagingMenu.odooBotNotificationsTab)) {
            return 0;
        }
        return this.shouldAskPushPermission ? 1 : 0;
    }

    /** @param {import("models").MessagingMenuTab} tab */
    onClickTab(tab) {
        log.logic("onClickTab", () => ({
            from: this.activeTab?.id,
            to: tab.id,
            collapsed: this.props.collapsed,
        }));
        if (this.props.collapsed) {
            this.props.onToggleCollapsed();
        }
        this.state.selectTab(tab);
    }

    /** @param {import("models").MessagingMenuTabFilter} [filter] */
    onClickFilter(filter) {
        this.state.selectFilter(filter);
    }

    /**
     * Filter groups an addon offers for the active tab, besides the tab's own filters:
     * each group selects at most one of its filters, combined with the tab's filter.
     *
     * @returns {MessagingMenuPluginFilterGroup[]}
     */
    get pluginFilterGroups() {
        return [];
    }

    get pluginFilterChipLimit() {
        return PLUGIN_FILTER_CHIP_LIMIT;
    }

    /** @param {string} key */
    selectedPluginFilter(key) {
        return this.state.pluginFilters[key];
    }

    /**
     * @param {string} key
     * @param {import("models").MessagingMenuTabFilter} filter
     */
    onClickPluginFilter(key, filter) {
        this.state.setPluginFilter(
            key,
            this.selectedPluginFilter(key)?.id === filter.id ? undefined : filter,
        );
    }

    /** @param {MessagingMenuTabAction} action */
    onClickAction(action) {
        log.logic("onClickAction", () => ({
            tab: this.activeTab?.id,
            action: action.id,
        }));
        action.onClick?.();
        if (!action.preventDropdownClose) {
            this.close();
        }
    }

    /** @param {InputEvent} ev */
    onInputSearch(ev) {
        this.state.searchTerm = /** @type {HTMLInputElement} */ (ev.target).value;
    }

    /**
     * @param {import("models").Message} message
     * @param {{isMarkAsRead?: boolean}} [options]
     */
    onClickMessage(message, { isMarkAsRead } = {}) {
        log.logic("onClickMessage", () => ({
            messageId: message.id,
            thread: message.thread?.localId,
            isMarkAsRead,
        }));
        if (isMarkAsRead) {
            message.setDone();
            return;
        }
        const thread = message.thread;
        if (!thread || message.message_type === "user_notification") {
            this.dialog.add(MessageInDialog, { message });
            if (message.needaction) {
                message.setDone();
            }
            this.close();
            return;
        }
        thread.highlightMessage = message;
        Promise.resolve(
            thread.open({ focus: true, fromMessagingMenu: true, bypassCompact: true }),
        )
            .then(() => {
                if (message.needaction) {
                    message.setDone();
                }
            })
            .catch((error) => {
                if (error?.exceptionName === "odoo.exceptions.AccessError") {
                    this.dialog.add(MessageInDialog, { message });
                    return;
                }
                throw error;
            });
        this.close();
    }

    /** @param {"first"|"last"|"previous"|"next"} direction */
    navigate(direction) {
        const items = this.navigableItems;
        const targetIndex = navigateIndex(
            direction,
            this.local.activeIndex,
            items.length,
        );
        if (targetIndex === undefined) {
            return;
        }
        this.local.activeIndex = targetIndex;
        items[targetIndex]?.scrollIntoView({ block: "nearest" });
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        if (!this.state.isDisplayed) {
            return;
        }
        if (!this.props.close && !this.rootRef.el?.contains(document.activeElement)) {
            return;
        }
        const hotkey = getActiveHotkey(ev);
        switch (hotkey) {
            case "enter":
                if (this.local.activeIndex === null) {
                    return;
                }
                log.logic("onKeydown opens item", () => ({
                    index: this.local.activeIndex,
                    prefixCount: this.prefixItems.length,
                }));
                this.navigableItems[this.local.activeIndex]?.click();
                break;
            case "tab":
            case "arrowdown":
                this.navigate(this.local.activeIndex === null ? "first" : "next");
                break;
            case "arrowup":
                this.navigate(this.local.activeIndex === null ? "first" : "previous");
                break;
            default:
                return;
        }
        ev.preventDefault();
        ev.stopPropagation();
    }

    /** @returns {HTMLElement[]} */
    get navigableItems() {
        const items = this.listRef.el?.querySelectorAll(".o-mail-NotificationItem");
        return /** @type {HTMLElement[]} */ ([...(items ?? [])]);
    }
}
