// @ts-check
/** @odoo-module native */
import { fields, Record } from "@mail/core/common/record";
import {
    readLocalStorageItem,
    removeLocalStorageItem,
    setLocalStorageItem,
} from "@mail/utils/common/local_storage";
import { router } from "@web/core/browser/router";
import { makeLogger } from "@web/core/debug/debug_logger";

const log = makeLogger("mail.discuss");
export const NO_MEMBERS_DEFAULT_OPEN_LS = "mail.user_setting.no_members_default_open";
export const DISCUSS_SIDEBAR_WIDTH_LS = "mail.user_setting.discuss_sidebar_width";
export const DISCUSS_SIDEBAR_COLLAPSED_LS =
    "mail.user_setting.discuss_sidebar_collapsed";
const LEGACY_SIDEBAR_COMPACT_LS = "mail.user_setting.discuss_sidebar_compact";
export const LAST_DISCUSS_ACTIVE_ID_LS = "mail.user_setting.discuss_last_active_id";

export const DISCUSS_SIDEBAR_STATE = "discuss.sidebar";
const SIDEBAR_WIDTH = 400;
export const SIDEBAR_MIN_WIDTH = 300;

export class DiscussApp extends Record {
    INSPECTOR_WIDTH = 300;
    isActive = false;
    sidebarState = fields.One("MessagingMenuUIState", {
        /** @this {import("models").DiscussApp} */
        compute() {
            return {
                id: DISCUSS_SIDEBAR_STATE,
                preferredTabId: this.store.inPublicPage ? "channel" : "chat",
            };
        },
    });
    isSidebarCollapsed = fields.Attr(false, {
        /** @this {import("models").DiscussApp} */
        compute() {
            const collapsed =
                readLocalStorageItem(this.store, DISCUSS_SIDEBAR_COLLAPSED_LS) ??
                readLocalStorageItem(this.store, LEGACY_SIDEBAR_COMPACT_LS);
            return collapsed === "true";
        },
        /** @this {import("models").DiscussApp} */
        onUpdate() {
            removeLocalStorageItem(this.store, LEGACY_SIDEBAR_COMPACT_LS);
            if (this.isSidebarCollapsed) {
                setLocalStorageItem(this.store, DISCUSS_SIDEBAR_COLLAPSED_LS, "true");
            } else {
                removeLocalStorageItem(this.store, DISCUSS_SIDEBAR_COLLAPSED_LS);
            }
        },
    });
    sidebarWidth = fields.Attr(SIDEBAR_WIDTH, {
        /** @this {import("models").DiscussApp} */
        compute() {
            const width = Number(
                readLocalStorageItem(this.store, DISCUSS_SIDEBAR_WIDTH_LS),
            );
            return width >= SIDEBAR_MIN_WIDTH ? width : SIDEBAR_WIDTH;
        },
        /** @this {import("models").DiscussApp} */
        onUpdate() {
            setLocalStorageItem(
                this.store,
                DISCUSS_SIDEBAR_WIDTH_LS,
                String(this.sidebarWidth),
            );
        },
    });
    isMemberPanelOpenByDefault = fields.Attr(true, {
        /** @this {import("models").DiscussApp} */
        compute() {
            return (
                readLocalStorageItem(this.store, NO_MEMBERS_DEFAULT_OPEN_LS) !== "true"
            );
        },
    });
    lastActiveId = fields.Attr(undefined, {
        /** @this {import("models").DiscussApp} */
        compute() {
            return (
                readLocalStorageItem(this.store, LAST_DISCUSS_ACTIVE_ID_LS) ?? undefined
            );
        },
        /** @this {import("models").DiscussApp} */
        onUpdate() {
            if (this.lastActiveId) {
                setLocalStorageItem(
                    this.store,
                    LAST_DISCUSS_ACTIVE_ID_LS,
                    this.lastActiveId,
                );
            } else {
                removeLocalStorageItem(this.store, LAST_DISCUSS_ACTIVE_ID_LS);
            }
        },
    });
    thread = fields.One("Thread", {
        /** @this {import("models").DiscussApp} */
        onUpdate() {
            this._threadOnUpdate();
        },
    });
    hasRestoredThread = false;

    /**
     * Writes the Discuss selection to the URL and to the Discuss action's context, which
     * breadcrumbs restore from: a thread (`discuss.channel_10`) or a tab
     * alone (`discuss.tab_channel`).
     *
     * @param {string} activeId
     */
    setActiveURL(activeId) {
        router.pushState({ active_id: activeId });
        const action = this.store.env.services.action;
        if (
            this.store.action_discuss_id &&
            action?.currentController?.action.id === this.store.action_discuss_id
        ) {
            action.currentController.action.context.active_id = activeId;
        }
    }

    /** @param {import("@mail/core/common/action").Action} [nextActiveAction] */
    shouldDisableMemberPanelAutoOpenFromClose(nextActiveAction) {
        return true;
    }

    _threadOnUpdate() {
        this.lastActiveId = this.store.Thread.localIdToActiveId(this.thread?.localId);
        log.logic("thread updated", () => ({
            thread: this.thread?.localId,
            lastActiveId: this.lastActiveId,
        }));
    }
}

DiscussApp.register();
