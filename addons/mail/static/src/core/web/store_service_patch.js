// @ts-check
/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { Store } from "@mail/core/common/store_service";
import { applyCounterAbsolute, snapshotCounter } from "@mail/utils/common/counters";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

const log = makeLogger("mail.store");
let unread_store;

/** Counters the server sends as of a bus id, which later bus deltas replay onto. */
const BUS_FENCED_COUNTERS = [
    "activityCounter",
    "needaction_counter",
    "starred_counter",
];

/**
 * Save the unread counter in the database shared with the service worker, so
 * that the app badge stays up to date.
 *
 * @param {number} counter
 * @param {boolean} [retry=true]
 */
async function saveUnreadCounter(counter, retry = true) {
    try {
        // opened lazily: idbKeyval is a classic library, read when first needed
        // rather than when this module evaluates
        unread_store ??= new window.idbKeyval.Store(
            "odoo-mail-unread-db",
            "odoo-mail-unread-store",
        );
    } catch {
        // the browser does not allow the database (private mode, blocked
        // storage): opening it again would fail the same way
        return;
    }
    try {
        await window.idbKeyval.set("unread", counter, unread_store);
    } catch {
        // the connection idbKeyval cached was closed by the browser: drop it so
        // the retry saves the counter on a new one
        unread_store = undefined;
        if (retry) {
            await saveUnreadCounter(counter, false);
        }
    }
}

/** @type {Partial<import("models").Store> & ThisType<import("models").Store>} */
const StorePatch = {
    setup() {
        super.setup();
        this.activityCounter = 0;
        this.activityCounter_bus_id = 0;
        /** @type {Object[]} */
        this.activityGroups = fields.Attr([], {
            /** @this {import("models").Store} */
            onUpdate() {
                this.onUpdateActivityGroups();
            },
            /** @this {import("models").Store} */
            sort(g1, g2) {
                /** @param {{id: number, model: string}} activityGroup */
                const getSortId = (activityGroup) =>
                    activityGroup.model === "mail.activity"
                        ? Number.MAX_VALUE
                        : activityGroup.id;
                return getSortId(g1) - getSortId(g2);
            },
        });
        this.globalCounter = fields.Attr(0, {
            /** @this {import("models").Store} */
            compute() {
                return this.computeGlobalCounter();
            },
            /** @this {import("models").Store} */
            onUpdate() {
                this.updateAppBadge();
            },
        });
        this.needaction_counter = 0;
        this.needaction_counter_bus_id = 0;
        this.starred_counter = 0;
        this.starred_counter_bus_id = 0;
        /** @type {Map<number, boolean[]>} */
        this.pendingStarToggles = new Map();
        this.messagingMenuSystrayState = fields.One("MessagingMenuUIState", {
            compute: () => ({ id: "mail.systray", preferredTabId: "chat" }),
        });
        /** @type {ReturnType<typeof import("@web/components/dropdown").useDropdownState>|undefined} */
        this.messagingMenuDropdown = undefined;
    },
    /** @param {Object} data */
    update(data) {
        if (typeof data !== "object" || data === null) {
            return super.update(data);
        }
        const values = /** @type {Object<string, any>} */ ({ ...data });
        /** @type {[string, number, number][]} */
        const absolutes = [];
        for (const field of BUS_FENCED_COUNTERS) {
            if (field in values && `${field}_bus_id` in values) {
                absolutes.push([field, values[field], values[`${field}_bus_id`]]);
                delete values[field];
                delete values[`${field}_bus_id`];
            }
        }
        const result = super.update(values);
        for (const [field, value, busId] of absolutes) {
            applyCounterAbsolute(this, field, value, busId);
        }
        return result;
    },
    computeGlobalCounter() {
        let counter = 0;
        for (const tab of this.messagingMenu.allTabs) {
            if (tab.appWide && tab.important) {
                counter += tab.counter - tab.extraCounter;
            }
        }
        return counter;
    },
    _getInitialFetchNames() {
        return ["failures", "systray_get_activities", ...super._getInitialFetchNames()];
    },
    onPushNotificationDisplayed() {
        super.onPushNotificationDisplayed(...arguments);
        this.updateAppBadge();
    },
    onStarted() {
        super.onStarted(...arguments);
        try {
            this.activityBroadcastChannel = new browser.BroadcastChannel(
                "mail.activity.channel",
            );
            this.activityBroadcastChannel.onmessage =
                this._onActivityBroadcastChannelMessage.bind(this);
        } catch {
            this.activityBroadcastChannel = null;
        }
        log.lifecycle("web onStarted", () => ({
            activityBroadcastChannel: Boolean(this.activityBroadcastChannel),
        }));
    },
    onUpdateActivityGroups() {},
    /**
     * @param {string | false} resModel
     * @param {(number | string)[] | false} resIds
     * @param {number|undefined} defaultActivityTypeId
     */
    async scheduleActivity(resModel, resIds, defaultActivityTypeId = undefined) {
        log.logic("scheduleActivity", () => ({
            resModel,
            resIds,
            defaultActivityTypeId,
        }));
        const context = {
            active_model: resModel,
            active_ids: resIds,
            active_id: resIds[0],
            ...(defaultActivityTypeId !== undefined
                ? { default_activity_type_id: defaultActivityTypeId }
                : {}),
        };
        await new Promise((resolve) =>
            this.env.services.action.doAction(
                {
                    type: "ir.actions.act_window",
                    name:
                        resIds && resIds.length > 1
                            ? _t("Schedule Activity On Selected Records")
                            : _t("Schedule Activity"),
                    res_model: "wizard.mail.activity.schedule",
                    view_mode: "form",
                    views: [[false, "form"]],
                    target: "new",
                    context,
                },
                {
                    onClose: resolve,
                    additionalContext: {
                        dialog_size: "large",
                    },
                },
            ),
        );
    },
    updateAppBadge() {
        log.logic("updateAppBadge", () => ({
            globalCounter: this.globalCounter,
            supported: Boolean(window.idbKeyval),
        }));
        if (window.idbKeyval) {
            saveUnreadCounter(this.globalCounter);
            Promise.resolve(navigator.setAppBadge?.(this.globalCounter)).catch(
                () => {},
            );
        }
    },
    /**
     * @param {object} param0
     * @param {({type: "INSERT"|"DELETE", payload: Partial<import("models").Activity>} | {type: "RELOAD_CHATTER", payload: {model: string, id: number}})} param0.data
     */
    _onActivityBroadcastChannelMessage({ data }) {
        log.pipeline("activity broadcast", () => ({
            type: data.type,
            payload: data.payload,
        }));
        switch (data.type) {
            case "INSERT":
                this.insert(data.payload, { broadcast: false });
                break;
            case "DELETE": {
                const activity = this["mail.activity"].insert(data.payload, {
                    broadcast: false,
                });
                activity.remove({ broadcast: false });
                break;
            }
            case "RELOAD_CHATTER": {
                const thread = this.Thread.insert({
                    model: data.payload.model,
                    id: data.payload.id,
                });
                thread.fetchNewMessages();
                thread.fetchThreadData?.(["activities"]);
                break;
            }
        }
    },
    async unstarAll() {
        const messages = Object.values(this["mail.message"].records).filter(
            (message) => message.starred,
        );
        const counterSnapshot = snapshotCounter(this, "starred_counter");
        log.logic("unstarAll", () => ({ messages: messages.length }));
        for (const message of messages) {
            message.starred = false;
        }
        this.starred_counter = 0;
        try {
            await this.env.services.orm.call("mail.message", "unstar_all");
        } catch (error) {
            log.logic("unstarAll rollback", () => ({ messages: messages.length }));
            for (const message of messages) {
                message.starred = true;
            }
            counterSnapshot.restore();
            throw error;
        }
    },
};
patch(Store.prototype, StorePatch);
