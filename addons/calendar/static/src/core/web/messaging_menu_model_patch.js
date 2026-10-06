/** @odoo-module native */
import { openScheduleMeeting } from "@calendar/core/web/schedule_meeting";
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

/** @type {Partial<import("models").MessagingMenu> & ThisType<import("models").MessagingMenu>} */
const messagingMenuPatch = {
    /** @param {string} tabId */
    extraTabActions(tabId) {
        const actions = super.extraTabActions(tabId);
        if (tabId !== MENU_TABS.MEETING || !this.store.selfIsInternalUser) {
            return actions;
        }
        return [
            ...actions,
            {
                id: "schedule_meeting",
                text: _t("Schedule for later"),
                onClick: () => openScheduleMeeting(this.store.env),
            },
        ];
    },
};
patch(MessagingMenu.prototype, messagingMenuPatch);
