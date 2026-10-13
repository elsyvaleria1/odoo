/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { getRootAppContext } from "@web/env";
import { Dropdown } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

export class PushNotificationWidget extends Interaction {
    static selector = "#wrapwrap";

    setup() {
        this.notification = this.services.notification;
    }

    async willStart() {
        const loadFirebaseAssets = () =>
            new Promise((resolve, reject) => {
                const script = document.createElement("script");
                script.addEventListener("load", () => {
                    resolve(globalThis.firebase);
                });
                script.addEventListener("error", (error) => {
                    reject(error);
                });
                script.type = "module";
                script.src = "/social_push_notifications/static/lib/firebase.js";
                document.head.appendChild(script);
            });
        try {
            this.firebase = await this.waitFor(loadFirebaseAssets());
        } catch {}
    }

    start() {
        if (!this._isBrowserCompatible() || !this.firebase) {
            return;
        }

        if (Notification.permission === "granted") {
            const { pushConfigurationPromise, wasUpdated } =
                this._getNotificationRequestConfiguration();
            pushConfigurationPromise.then((pushConfiguration) => {
                if (Object.keys(pushConfiguration).length === 1) {
                    return;
                }
                const messaging = this._initializeFirebaseApp(pushConfiguration);
                if (wasUpdated) {
                    this._registerServiceWorker(pushConfiguration, messaging);
                }
                this._setForegroundNotificationHandler(pushConfiguration, messaging);
            });
        } else if (Notification.permission !== "denied") {
            this._askPermission();
        }
        this.addListener(getRootAppContext().bus, "open_notification_request", (ev) =>
            this._onNotificationRequest(...ev.detail),
        );
    }

    /** @private */
    _setForegroundNotificationHandler(config, messaging) {
        const onMessage = (payload) => {
            if (window.Notification && Notification.permission === "granted") {
                const options = {
                    title: payload.notification.title,
                    type: "success",
                };
                if (payload.data && payload.data.target_url) {
                    options.buttons = [
                        {
                            name: "Open",
                            onClick: () =>
                                window.open(payload.data.target_url, "_blank"),
                        },
                    ];
                }
                this.notification.add(payload.notification.body, options);
            }
        };
        messaging = messaging || this._initializeFirebaseApp(config);
        if (!messaging) {
            return;
        }
        this.firebase.onMessage(messaging, onMessage);
    }

    /** @private */
    _isBrowserCompatible() {
        if (!("serviceWorker" in navigator)) {
            return false;
        }

        if (!("PushManager" in window)) {
            return false;
        }

        return true;
    }

    /**
     * @param {Object} config
     * @returns {firebase.messaging.Messaging}
     * @private
     */
    _initializeFirebaseApp(config) {
        if (
            !config.firebase_push_certificate_key ||
            !config.firebase_project_id ||
            !config.firebase_web_api_key ||
            !config.firebase_web_app_id
        ) {
            return null;
        }

        const app = this.firebase.initializeApp({
            appId: config.firebase_web_app_id,
            apiKey: config.firebase_web_api_key,
            projectId: config.firebase_project_id,
            messagingSenderId: config.firebase_sender_id,
        });

        return this.firebase.getMessaging(app);
    }

    /**
     * @param {Object} config
     * @param {firebase.messaging.Messaging} messaging
     * @private
     */
    _registerServiceWorker(config, messaging) {
        messaging = messaging || this._initializeFirebaseApp(config);
        if (!messaging) {
            return;
        }

        const url = new URL(
            window.location.origin +
                "/social_push_notifications/static/src/js/push_service_worker.js",
        );
        url.searchParams.append("appId", config.firebase_web_app_id);
        url.searchParams.append("apiKey", config.firebase_web_api_key);
        url.searchParams.append("projectId", config.firebase_project_id);
        url.searchParams.append("messagingSenderId", config.firebase_sender_id);

        navigator.serviceWorker
            .register(url, { type: "module" })
            .then((registration) => {
                this.firebase
                    .getToken(messaging, {
                        vapidKey: config.firebase_push_certificate_key,
                        serviceWorkerRegistration: registration,
                    })
                    .then((token) => {
                        this._registerToken(token);
                    });
            });
    }

    /** @private */
    _isConfigurationUpToDate(pushConfiguration) {
        if (pushConfiguration) {
            if (new Date() < new Date(pushConfiguration.expirationDate)) {
                return true;
            }
        }

        return false;
    }

    /** @private */
    _fetchPushConfiguration() {
        return rpc("/social_push_notifications/get_push_configuration").then(
            (config) => {
                const expirationDate = new Date();
                expirationDate.setDate(expirationDate.getDate() + 7);
                Object.assign(config, { expirationDate: expirationDate });
                browser.localStorage.setItem(
                    "social_push_notifications.notification_request_config",
                    JSON.stringify(config),
                );
                return config;
            },
        );
    }

    /** @param {string} token */
    _registerToken(token) {
        const pushConfiguration = this._getPushConfiguration();
        if (pushConfiguration && pushConfiguration.token !== token) {
            rpc("/social_push_notifications/unregister", {
                token: pushConfiguration.token,
            });
        }

        rpc("/social_push_notifications/register", {
            token: token,
        }).then(() => {
            browser.localStorage.setItem(
                "social_push_notifications.configuration",
                JSON.stringify({
                    token: token,
                }),
            );
        });
    }

    /**
     * @param {String} [nextAskPermissionKeySuffix]
     * @param {Object} [forcedPopupConfig]
     * @param {String} forcedPopupConfig.title
     * @param {String} forcedPopupConfig.body
     * @param {String} forcedPopupConfig.delay
     * @param {String} forcedPopupConfig.icon
     */
    async _askPermission(nextAskPermissionKeySuffix, forcedPopupConfig) {
        const nextAskPermission = browser.localStorage.getItem(
            "social_push_notifications.next_ask_permission" +
                (nextAskPermissionKeySuffix ? "." + nextAskPermissionKeySuffix : ""),
        );
        if (nextAskPermission && new Date() < new Date(nextAskPermission)) {
            return;
        }

        const { pushConfigurationPromise } =
            this._getNotificationRequestConfiguration();
        const pushConfiguration = await this.waitFor(pushConfigurationPromise);
        if (Object.keys(pushConfiguration).length === 1) {
            return;
        }
        let popupConfig = {
            title: pushConfiguration.notification_request_title,
            body: pushConfiguration.notification_request_body,
            delay: pushConfiguration.notification_request_delay,
            icon: pushConfiguration.notification_request_icon,
        };

        if (!popupConfig || !popupConfig.title || !popupConfig.body) {
            return;
        }
        if (forcedPopupConfig) {
            popupConfig = Object.assign({}, popupConfig, forcedPopupConfig);
        }
        this._showNotificationRequestPopup(
            popupConfig,
            pushConfiguration,
            nextAskPermissionKeySuffix,
        );
    }

    /**
     * @param {Object} popupConfig
     * @param {Object} pushConfig
     * @param {String} [nextAskPermissionKeySuffix]
     */
    _showNotificationRequestPopup(popupConfig, pushConfig, nextAskPermissionKeySuffix) {
        const selector = ".o_social_push_notifications_permission_request";
        if (
            !popupConfig.title ||
            !popupConfig.body ||
            this.el.querySelectorAll(selector).length > 0
        ) {
            return;
        }

        const [popupEl] = this.renderAt(
            "social_push_notifications.NotificationRequestPopup",
            {
                notificationTitle: popupConfig.title,
                notificationBody: popupConfig.body,
                notificationIcon: popupConfig.icon,
            },
        );

        if (document.getElementById("oe_main_menu_navbar")) {
            popupEl.classList.add(
                "o_social_push_notifications_permission_with_menubar",
            );
        }

        this.waitForTimeout(() => {
            const toggleEl = popupEl.querySelector(".dropdown-toggle");
            if (toggleEl) {
                new Dropdown(toggleEl).toggle();
            }
        }, popupConfig.delay * 1000);

        const dropdown = popupEl.querySelector(".dropdown");
        if (dropdown) {
            this.addListener(dropdown, "hide.bs.dropdown", () => popupEl.remove());
        }
        this.addListener(
            popupEl.querySelector(".o_social_push_notifications_permission_allow"),
            "click",
            () => {
                Notification.requestPermission().then(() => {
                    if (Notification.permission === "granted") {
                        const messaging = this._initializeFirebaseApp(pushConfig);
                        this._registerServiceWorker(pushConfig, messaging);
                        this._setForegroundNotificationHandler(pushConfig, messaging);
                    }
                });
            },
        );
        this.addListener(
            popupEl.querySelector(".o_social_push_notifications_permission_deny"),
            "click",
            () => {
                const nextAskPermissionDate = new Date();
                nextAskPermissionDate.setDate(nextAskPermissionDate.getDate() + 7);
                browser.localStorage.setItem(
                    "social_push_notifications.next_ask_permission" +
                        (nextAskPermissionKeySuffix
                            ? "." + nextAskPermissionKeySuffix
                            : ""),
                    nextAskPermissionDate,
                );
            },
        );
    }

    _getPushConfiguration() {
        return this._getJSONLocalStorageItem("social_push_notifications.configuration");
    }

    /**
     * @returns {Promise, boolean}
     * @private
     */
    _getNotificationRequestConfiguration() {
        const pushConfiguration = this._getJSONLocalStorageItem(
            "social_push_notifications.notification_request_config",
        );

        const wasUpdated = !this._isConfigurationUpToDate(pushConfiguration);
        const pushConfigurationPromise = wasUpdated
            ? this._fetchPushConfiguration()
            : Promise.resolve(pushConfiguration);

        return { pushConfigurationPromise, wasUpdated };
    }

    _getJSONLocalStorageItem(key) {
        const value = browser.localStorage.getItem(key);
        if (value) {
            return JSON.parse(value);
        }

        return null;
    }

    /**
     * @param {String} [nextAskPermissionKeySuffix]
     * @param {Object} [forcedPopupConfig]
     * @param {String} forcedPopupConfig.title
     * @param {String} forcedPopupConfig.body
     * @param {String} forcedPopupConfig.delay
     * @param {String} forcedPopupConfig.icon
     */
    async _onNotificationRequest(nextAskPermissionKeySuffix, forcedPopupConfig) {
        if (Notification.permission !== "default") {
            return;
        }
        this._askPermission(nextAskPermissionKeySuffix, forcedPopupConfig);
    }
}

registry
    .category("public.interactions")
    .add("social_push_notifications.push_notification_widget", PushNotificationWidget);
