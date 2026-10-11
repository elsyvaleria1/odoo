/** @odoo-module native */
import { markup } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { ConnectionLostError, rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

const MIN_REPOLL_DELAY_SECONDS = 60;

export const calendarNotificationService = {
    dependencies: ["action", "bus_service", "notification"],

    start(env, { action, bus_service, notification }) {
        let calendarNotifTimeouts = {};
        let nextCalendarNotifTimeout = null;
        const displayedNotifications = new Set();

        bus_service.subscribe("calendar.alarm", (payload) => {
            displayCalendarNotification(payload);
        });
        bus_service.start();

        function displayCalendarNotification(notifications) {
            let lastNotifTimer = 0;

            browser.clearTimeout(nextCalendarNotifTimeout);
            Object.values(calendarNotifTimeouts).forEach((notif) =>
                browser.clearTimeout(notif),
            );
            calendarNotifTimeouts = {};

            notifications.forEach(function (notif) {
                const key = notif.event_id + "," + notif.alarm_id;
                if (displayedNotifications.has(key)) {
                    return;
                }
                calendarNotifTimeouts[key] = browser.setTimeout(function () {
                    const notificationRemove = notification.add(markup(notif.message), {
                        title: notif.title,
                        type: "warning",
                        sticky: true,
                        onClose: () => {
                            displayedNotifications.delete(key);
                        },
                        buttons: [
                            {
                                name: _t("OK"),
                                primary: true,
                                onClick: async () => {
                                    await rpc("/calendar/notify_ack");
                                    notificationRemove();
                                },
                            },
                            {
                                name: _t("Details"),
                                onClick: async () => {
                                    await action.doAction({
                                        type: "ir.actions.act_window",
                                        res_model: "calendar.event",
                                        res_id: notif.event_id,
                                        views: [[false, "form"]],
                                    });
                                    notificationRemove();
                                },
                            },
                            {
                                name: _t("Snooze"),
                                onClick: () => {
                                    notificationRemove();
                                },
                            },
                        ],
                    });
                    displayedNotifications.add(key);
                }, notif.timer * 1000);
                lastNotifTimer = Math.max(lastNotifTimer, notif.timer);
            });

            if (notifications.length) {
                nextCalendarNotifTimeout = browser.setTimeout(
                    getNextCalendarNotif,
                    Math.max(lastNotifTimer, MIN_REPOLL_DELAY_SECONDS) * 1000,
                );
            }
        }

        async function getNextCalendarNotif() {
            try {
                const result = await rpc("/calendar/notify", {}, { silent: true });
                displayCalendarNotification(result);
            } catch (error) {
                if (!(error instanceof ConnectionLostError)) {
                    throw error;
                }
            }
        }
    },
};

registry.category("services").add("calendarNotification", calendarNotificationService);
