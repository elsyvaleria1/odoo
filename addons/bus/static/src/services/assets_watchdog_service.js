/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { session } from "@web/session";

export const assetsWatchdogService = {
    dependencies: ["bus_service", "notification"],

    start(env, { bus_service, notification }) {
        let isNotificationDisplayed = false;
        let bundleNotifTimerID = null;

        bus_service.subscribe("bundle_changed", ({ server_version }) => {
            if (server_version !== session.server_version) {
                displayBundleChangedNotification();
            }
        });
        bus_service.start();

        function displayBundleChangedNotification() {
            if (!isNotificationDisplayed && bundleNotifTimerID === null) {
                bundleNotifTimerID = browser.setTimeout(() => {
                    bundleNotifTimerID = null;
                    notification.add(_t("The page appears to be out of date."), {
                        title: _t("Refresh"),
                        type: "warning",
                        sticky: true,
                        buttons: [
                            {
                                name: _t("Refresh"),
                                primary: true,
                                onClick: () => {
                                    browser.location.reload();
                                },
                            },
                        ],
                        onClose: () => {
                            isNotificationDisplayed = false;
                        },
                    });
                    isNotificationDisplayed = true;
                }, getBundleNotificationDelay());
            }
        }

        /** @return {number} */
        function getBundleNotificationDelay() {
            return 10000 + Math.floor(Math.random() * 50) * 1000;
        }
    },
};

registry.category("services").add("bus.assets_watchdog", assetsWatchdogService);
