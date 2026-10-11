/** @odoo-module native */
import { lastNotificationIdKey } from "@bus/services/bus_service";
import { CONNECTION_STATE } from "@bus/workers/websocket_worker_constants";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { session } from "@web/session";

export function hasMissedNotificationsKey() {
    return `${session.db}.bus.has_missed_notifications`;
}

export class OutdatedPageWatcherService {
    constructor(env, services) {
        this.setup(env, services);
    }

    /**
     * @param {import("@web/env").OdooEnv}
     * @param {Partial<import("services").Services>} services
     */
    setup(env, { bus_service, multi_tab, shared_storage, notification }) {
        this.notification = notification;
        this.multi_tab = multi_tab;
        this.shared_storage = shared_storage;
        this.lastNotificationId = shared_storage.getSharedValue(
            lastNotificationIdKey(),
        );
        this.closeNotificationFn = undefined;
        let wasBusAlreadyConnected;
        bus_service.addEventListener(
            "BUS:WORKER_STATE_UPDATED",
            ({ detail: state }) => {
                wasBusAlreadyConnected = state === CONNECTION_STATE.CONNECTED;
            },
            { once: true },
        );
        bus_service.addEventListener("BUS:OUTDATED", () =>
            this.showOutdatedPageNotification(),
        );
        bus_service.addEventListener(
            "BUS:DISCONNECT",
            () =>
                (this.lastNotificationId = shared_storage.getSharedValue(
                    lastNotificationIdKey(),
                )),
        );
        bus_service.addEventListener("BUS:CONNECT", async () => {
            if (wasBusAlreadyConnected) {
                this.checkHasMissedNotifications();
            }
            wasBusAlreadyConnected = true;
        });
        bus_service.addEventListener("BUS:RECONNECT", () => {
            if (wasBusAlreadyConnected) {
                this.checkHasMissedNotifications();
            }
            wasBusAlreadyConnected = true;
        });
        shared_storage.bus.addEventListener(
            "shared_value_updated",
            ({ detail: { key } }) => {
                if (key === hasMissedNotificationsKey()) {
                    this.showOutdatedPageNotification();
                }
            },
        );
    }

    async checkHasMissedNotifications() {
        if (!this.lastNotificationId || !(await this.multi_tab.isOnMainTab())) {
            return;
        }
        const hasMissedNotifications = await rpc(
            "/bus/has_missed_notifications",
            { last_notification_id: this.lastNotificationId },
            { silent: true },
        );
        if (hasMissedNotifications) {
            this.showOutdatedPageNotification();
            this.shared_storage.setSharedValue(hasMissedNotificationsKey(), Date.now());
        }
    }

    showOutdatedPageNotification() {
        this.closeNotificationFn?.();
        this.closeNotificationFn = this.notification.add(
            _t(
                "Save your work and refresh to get the latest updates and avoid potential issues.",
            ),
            {
                title: _t("The page is out of date"),
                type: "warning",
                sticky: true,
                buttons: [
                    {
                        name: _t("Refresh"),
                        primary: true,
                        onClick: () => browser.location.reload(),
                    },
                ],
            },
        );
    }
}

export const outdatedPageWatcherService = {
    dependencies: ["bus_service", "multi_tab", "shared_storage", "notification"],
    start(env, services) {
        return new OutdatedPageWatcherService(env, services);
    },
};

registry
    .category("services")
    .add("bus.outdated_page_watcher", outdatedPageWatcherService);
