// @ts-check
/** @odoo-module native */
import { applyCounterDelta } from "@mail/utils/common/counters";
import { proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
const log = makeLogger("mail.bus");

export class MailCoreWeb {
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {import("services").ServiceFactories} services
     */
    constructor(env, services) {
        this.env = env;
        this.busService = services.bus_service;
        this.store = services["mail.store"];
    }

    _subscribeActivityUpdated() {
        this.busService.subscribe(
            "mail.activity/updated",
            /**
             * @param {Object} payload
             * @param {number} [payload.count_diff]
             * @param {boolean} [payload.activity_created]
             * @param {boolean} [payload.activity_deleted]
             * @param {{id: number}} metadata
             */
            (payload, { id: notifId }) => {
                log.pipeline("mail.activity/updated", () => payload);
                let countDiff = 0;
                if ("count_diff" in payload) {
                    countDiff = payload.count_diff;
                } else if (payload.activity_created) {
                    countDiff = 1;
                } else if (payload.activity_deleted) {
                    countDiff = -1;
                }
                applyCounterDelta(this.store, "activityCounter", countDiff, {
                    busId: notifId,
                });
            },
        );
    }
    _subscribeMessageDeleted() {
        this.env.bus.addEventListener(
            "mail.message/delete",
            /** @param {CustomEvent<{message: import("models").Message, notifId: number}>} ev */
            ({ detail: { message, notifId } }) => {
                log.pipeline("mail.message/delete counters", () => ({
                    messageId: message.id,
                    needaction: message.needaction,
                    starred: message.starred,
                }));
                if (message.needaction && message.countsInNotifications) {
                    applyCounterDelta(this.store, "needaction_counter", -1, {
                        busId: notifId,
                    });
                }
                if (message.starred) {
                    applyCounterDelta(this.store, "starred_counter", -1, {
                        busId: notifId,
                    });
                }
                const thread = message.thread;
                if (message.needaction && thread) {
                    applyCounterDelta(thread, "message_needaction_counter", -1, {
                        busId: notifId,
                    });
                }
            },
        );
    }
    _subscribeNeedactionMessages() {
        this.busService.subscribe(
            "mail.message/needaction",
            /**
             * @param {{message_id: number, needaction_delta: number, store_data: Object}} payload
             * @param {{id: number}} metadata
             */
            (payload, { id: notifId }) => {
                log.pipeline("mail.message/needaction", () => payload);
                const { message_id: messageId, needaction_delta, store_data } = payload;
                this.store.insert(store_data);
                applyCounterDelta(this.store, "needaction_counter", needaction_delta, {
                    busId: notifId,
                });
                /** @type {import("models").Message} */
                const message = this.store["mail.message"].get(messageId);
                if (!message) {
                    log.logic(
                        "mail.message/needaction message missing after insert",
                        () => ({
                            messageId,
                        }),
                    );
                    return;
                }
                if (message.thread) {
                    applyCounterDelta(message.thread, "message_needaction_counter", 1, {
                        busId: notifId,
                    });
                }
                if (this.store.self_partner?.im_status?.includes("busy")) {
                    log.logic("mail.message/needaction notification suppressed: busy");
                    return;
                }
                this.store.env.services["mail.out_of_focus"].notify(message);
            },
        );
    }
    _subscribeMarkedAsRead() {
        this.busService.subscribe(
            "mail.message/mark_as_read",
            /**
             * @param {{message_ids: number[], needaction_delta: number}} payload
             * @param {{id: number}} metadata
             */
            (payload, { id: notifId }) => {
                log.pipeline("mail.message/mark_as_read", () => payload);
                const { message_ids: messageIds, needaction_delta } = payload;
                for (const messageId of messageIds) {
                    const message = this.store["mail.message"].get(messageId);
                    if (!message) {
                        continue;
                    }
                    const thread = message.thread;
                    if (thread && message.needaction) {
                        applyCounterDelta(thread, "message_needaction_counter", -1, {
                            busId: notifId,
                        });
                    }
                    message.needaction = false;
                    message.needaction_done = true;
                }
                applyCounterDelta(this.store, "needaction_counter", needaction_delta, {
                    busId: notifId,
                });
            },
        );
    }
    setup() {
        this._subscribeActivityUpdated();
        this._subscribeMessageDeleted();
        this._subscribeNeedactionMessages();
        this._subscribeMarkedAsRead();
    }
}

export const mailCoreWeb = {
    dependencies: ["bus_service", "mail.store"],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {import("services").ServiceFactories} services
     */
    start(env, services) {
        const mailCoreWeb = proxy(new MailCoreWeb(env, services));
        mailCoreWeb.setup();
        return mailCoreWeb;
    },
};

registry.category("services").add("mail.core.web", mailCoreWeb);
