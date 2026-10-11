/** @odoo-module native */

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.2/firebase-app.js";
import {
    getMessaging,
    onBackgroundMessage,
} from "https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-sw.js";

const getFirebaseConfig = () => {
    const params = new URLSearchParams(self.location.search);
    return {
        appId: params.get("appId"),
        apiKey: params.get("apiKey"),
        projectId: params.get("projectId"),
        messagingSenderId: params.get("messagingSenderId"),
    };
};

const app = initializeApp(getFirebaseConfig());
const messaging = getMessaging(app);

self.addEventListener("notificationclick", function (event) {
    if (event.action === "close") {
        event.notification.close();
    } else if (
        event.notification.data.target_url &&
        "" !== event.notification.data.target_url.trim()
    ) {
        clients.openWindow(event.notification.data.target_url);
    }
});

onBackgroundMessage(messaging, function (payload) {
    const options = {
        body: payload.notification.body,
        icon: payload.notification.image,
    };
    if (payload.data && payload.data.target_url) {
        options.data = {
            target_url: payload.data.target_url,
        };
    }
    return self.registration.showNotification(payload.notification.title, options);
});
