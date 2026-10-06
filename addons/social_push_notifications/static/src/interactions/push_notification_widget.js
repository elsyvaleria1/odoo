/** @odoo-module native */

/** @module @social_push_notifications/interactions/push_notification_widget - Firebase web push notifications: permission request popup + token registration */

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

    /**
     * Firebase dependencies are now provided as standard JavaScript modules.
     * To ensure the browser recognizes and executes these scripts correctly,
     * they must be loaded using a `<script>` tag with `type="module"`.
     * Unfortunately, these dependencies cannot be included in the common
     * Odoo JS bundle because the bundle is loaded with a `<script>` tag
     * having `type="text/javascript"`. This difference prevents the browser
     * from recognizing modern JavaScript module-specific syntax that are
     * used in the Firebase dependencies (see: `import` and `export`).
     * To load the dependencies, we have to manually inject in the DOM a
     * script tag with the "module" type.
     */
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
        } catch {
            // Firebase could not be loaded: the interaction stays inert.
        }
    }

    /**
     * This will start listening to notifications if permission was already
     * granted by the user or ask for permission after a timeout (configurable)
     * and then start listening.
     */
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

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Will handle Firebase Messaging foreground notifications.
     *
     * The push notifications will only be displayed is the user has
     * granted notification permission to the website.
     *
     * See: https://rnfirebase.io/messaging/usage#foreground-state-messages
     *
     * @private
     */
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

    /**
     * Will check browser compatibility before trying to register the service worker.
     * Browsers compatible now (11/07/2019):
     * - Chrome
     * - Firefox
     * - Edge
     *
     * For Safari we would need to use an entirely different service since they have their own
     * push notifications mechanism.
     * See: https://developer.apple.com/notifications/safari-push-notifications/
     *
     * @private
     */
    _isBrowserCompatible() {
        if (!("serviceWorker" in navigator)) {
            // Service Worker isn't supported on this browser
            return false;
        }

        if (!("PushManager" in window)) {
            // Push isn't supported on this browser
            return false;
        }

        return true;
    }

    /**
     * Will initialize the firebase app with the given configuration
     * and return the messaging object.
     *
     * @param {Object} config the push configuration
     * @returns {firebase.messaging.Messaging}
     *
     * @private
     */
    _initializeFirebaseApp(config) {
        if (
            !config.firebase_push_certificate_key ||
            !config.firebase_project_id ||
            !config.firebase_web_api_key ||
            !config.firebase_web_app_id
        ) {
            // missing configuration
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
     * Will register a service worker to display later notifications.
     * This method also handles the notification "subscription token".
     *
     * The token will be used by firebase to notify this user directly.
     *
     * @param {Object} config the push configuration
     * @param {firebase.messaging.Messaging} messaging
     *
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

    /**
     * Checks that the push notification configuration is still up to date.
     * (It expires after 7 days)
     *
     * @private
     */
    _isConfigurationUpToDate(pushConfiguration) {
        if (pushConfiguration) {
            if (new Date() < new Date(pushConfiguration.expirationDate)) {
                return true;
            }
        }

        return false;
    }

    /**
     * Responsible for fetching the full push configuration.
     *
     * When the configuration is fetched, it's stored into local storage (for 7 days)
     * to save future requests.
     *
     * @private
     */
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

    /**
     * Will register the subscription token into database for later notifications
     *
     * We store the token in the localStorage for 7 days to avoid having to save
     * it every time the user loads a website page.
     *
     * If the token from localStorage is different from the one we are registering, we clean
     * the old one from the registrations.
     *
     * @param {string} token
     */
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
     * We work with 2 different permission request popups:
     *
     * - The first one is a regular bootstrap popup configurable (title,text,...) from the backend.
     *   It has an accept and a deny buttons. It also closes if the user clicks outside.
     *
     * -> if closed by clicking outside/on cross, will re-open on next page reload
     * -> if closed by clicking 'Deny', will re-open after 7 days on page reload
     * -> if closed by clicking on 'Allow', triggers the second popup.
     *
     * - The second popup is the one opened by the browser when asking for notifications permission.
     *
     * -> if closed by clicking outside/on cross, will re-open the first popup on next page reload
     * -> if closed by clicking on 'Block', we will not be allowed to send notifications to that user.
     * -> if closed by clicking on 'Allow', we register a service worker to send notifications.
     *
     * In addition to that, the first popup configuration (title,text,...) is stored into localStorage
     * to avoid having to fetch it on every page reload if the user doesn't accept or deny the popup.
     *
     * The configuration is stored for 7 days to still receive visual updates if the configuration
     * changes on the backend side.
     *
     * @param {String} [nextAskPermissionKeySuffix] optional - Suffix of the cache entry
     * @param {Object} [forcedPopupConfig] optional - Properties that will overwrite the notification request configuration.
     * @param {String} forcedPopupConfig.title optional - Title of the popup.
     * @param {String} forcedPopupConfig.body optional - Body of the popup.
     * @param {String} forcedPopupConfig.delay optional - Delay of the popup.
     * @param {String} forcedPopupConfig.icon optional - Icon of the popup.
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
            return; // this means that the web push notifications are not enabled in the settings
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
     * Method responsible for the display of the Notification Request Popup.
     * The popup is rendered from the qweb template and wired here directly
     * (it was previously a dedicated legacy child widget):
     * - after the configured delay, the bootstrap dropdown opens;
     * - 'Allow' triggers the browser permission request and, when granted,
     *   the service worker / foreground handler registration;
     * - 'Deny' snoozes the request for 7 days;
     * - closing the dropdown (outside click, cross, or any button — bootstrap
     *   auto-close) removes the popup from the DOM.
     *
     * @param {Object} popupConfig the popup configuration (title,body,...)
     * @param {Object} pushConfig the push configuration
     * @param {String} [nextAskPermissionKeySuffix] optional
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

        // Push down the notification window if the main menu nav bar is active.
        // (We want to avoid covering the nav bar with the notification window)
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
     * Get the notification request configuration.
     *
     * The configuration is first retrieved from local storage if it's still valid.
     * If not, it will be fetched from the server.
     *
     * @returns {Promise, boolean} the push configuration as a promise and a boolean
     * indicating if the configuration was updated.
     *
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
     * The module will guarantee that no other push notification request for
     * the `nextAskPermissionKeySuffix` key will issued if the user dismissed
     * a request using the same key within the last 7 days.
     *
     * This can be useful in specific context, e.g:
     * When favoriting event.tracks, we want to re-ask the user to enable the push
     * notifications even if the user recently dismisses the default one. By
     * using a custom key, we can issue a new request without having to wait that
     * the 7 days restriction set by the first request expires. When the user
     * dismisses the new request, a 7 days restriction will also be applied to the
     * provided key.
     *
     * @param {String} [nextAskPermissionKeySuffix] Suffix of the cache entry.
     * @param {Object} [forcedPopupConfig] Properties of the popup.
     * @param {String} forcedPopupConfig.title optional - Title of the popup.
     * @param {String} forcedPopupConfig.body optional - Body of the popup.
     * @param {String} forcedPopupConfig.delay optional - Delay of the popup.
     * @param {String} forcedPopupConfig.icon optional - Icon of the popup.
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
