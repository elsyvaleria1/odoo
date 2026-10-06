// @ts-check
/** @odoo-module native */
import { DISCUSS_SIDEBAR_STATE } from "@mail/core/public_web/discuss_app_model";
import { MessagingMenuUIState } from "@mail/core/public_web/messaging_menu/messaging_menu_ui_state_model";
import { patch } from "@web/core/utils/patch";

/** @type {Partial<import("models").MessagingMenuUIState> & ThisType<import("models").MessagingMenuUIState>} */
const uiStatePatch = {
    /** @param {import("models").MessagingMenuTab} tab */
    selectTab(tab) {
        const reselected = Boolean(this.activeTab?.eq(tab));
        super.selectTab(tab);
        if (this.id === DISCUSS_SIDEBAR_STATE && !reselected) {
            this.store.discuss.thread = undefined;
            this.store.discuss.setActiveURL(`discuss.tab_${tab.id}`);
        }
    },
    _isReadyForInitialLoad() {
        if (
            this.id === DISCUSS_SIDEBAR_STATE &&
            !this.store.discuss?.hasRestoredThread
        ) {
            return false;
        }
        return super._isReadyForInitialLoad();
    },
};
patch(MessagingMenuUIState.prototype, uiStatePatch);
