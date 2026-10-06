// @ts-check
/** @odoo-module native */
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { fields } from "@mail/model/misc";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.BOOKMARK = "bookmark";
MENU_TABS.NOTIFICATION = "notification";

/** @type {Partial<import("models").MessagingMenu> & ThisType<import("models").MessagingMenu>} */
const messagingMenuPatch = {
    setup() {
        super.setup();
        this.bookmarkTab = fields.One("MessagingMenuTab", {
            /** @this {import("models").MessagingMenu} */
            compute() {
                if (!this.store.selfIsInternalUser) {
                    return;
                }
                return {
                    id: MENU_TABS.BOOKMARK,
                    important: false,
                    storeCounter: "starred_counter",
                    recordType: "mail.message",
                    messageActionIds: ["toggle-star", "copy-link"],
                    /** @param {import("models").Message} message */
                    includesMessage: (message) => Boolean(message.starred),
                    icon: "fa-solid fa-bookmark",
                    sequence: 120,
                    label: _t("Bookmarks"),
                    hideWhenZeroCounter: true,
                    actions: [
                        {
                            id: "remove-all-bookmarks",
                            text: _t("Remove all"),
                            isDisabled: () => !this.bookmarkTab?.counter,
                            onClick: () => this.store.unstarAll(),
                            preventDropdownClose: true,
                        },
                    ],
                };
            },
        });
        this.notificationTab = fields.One("MessagingMenuTab", {
            /** @this {import("models").MessagingMenu} */
            compute() {
                if (!this.store.selfUsesInbox) {
                    return;
                }
                return {
                    id: MENU_TABS.NOTIFICATION,
                    recordType: "mail.message",
                    storeCounter: "needaction_counter",
                    messageActionIds: [
                        "mark-as-read",
                        "toggle-star",
                        "reply-all",
                        "forward",
                        "download_files",
                        "copy-link",
                    ],
                    /** @param {import("models").Message} message */
                    includesMessage: (message) =>
                        Boolean(message.needaction || message.needaction_done) &&
                        this.notificationMatchesExtra(message),
                    icon: "fa-solid fa-bell",
                    sequence: 60,
                    label: _t("Notifications"),
                    emptyState: {
                        title: _t("You're all caught up!"),
                        subtitle: _t(
                            "Notifications of the documents you follow will appear here.",
                        ),
                    },
                    filters: [
                        {
                            id: "notification_unread",
                            text: _t("Unread"),
                            /** @param {import("models").Message} message */
                            includesMessage: (message) =>
                                Boolean(message.needaction) &&
                                this.notificationMatchesExtra(message),
                            isDefault: true,
                        },
                    ],
                    actions: [
                        {
                            id: "mark-all-read",
                            text: _t("Mark all read"),
                            isDisabled: () => !this.notificationTab?.counter,
                            onClick: () =>
                                this.store.env.services.orm.silent.call(
                                    "mail.message",
                                    "mark_all_as_read",
                                ),
                            preventDropdownClose: true,
                        },
                    ],
                };
            },
        });
    },
};
patch(MessagingMenu.prototype, messagingMenuPatch);
