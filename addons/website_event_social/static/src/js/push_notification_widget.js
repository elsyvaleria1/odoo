/** @odoo-module native */

import { PushNotificationWidget } from "@social_push_notifications/interactions/push_notification_widget";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(PushNotificationWidget.prototype, {
    _askPermission() {
        if (!document.querySelector(".o_wereg_js_confirmed")) {
            return super._askPermission(...arguments);
        }

        return this._fetchPushConfiguration().then((config) => {
            this._showNotificationRequestPopup(
                {
                    title: config.notification_request_title,
                    body: config.notification_request_body,
                    delay: config.notification_request_delay,
                    icon: config.notification_request_icon,
                },
                config,
            );
        });
    },

    _showNotificationRequestPopup(popupConfig, pushConfig) {
        if (!document.querySelector(".o_wereg_js_confirmed")) {
            return super._showNotificationRequestPopup(...arguments);
        }

        if (popupConfig.title && popupConfig.body) {
            popupConfig.title = _t("Get the best experience!");
            popupConfig.body = _t(
                "Allow notifications to be able to add talks into your favorite list or connect to other attendees.",
            );
            popupConfig.delay = 0;
        }

        return super._showNotificationRequestPopup(popupConfig, pushConfig);
    },
});
