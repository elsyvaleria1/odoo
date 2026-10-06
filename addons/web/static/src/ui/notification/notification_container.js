// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { reportUncaught } from "@web/core/errors/error_utils";
import { Transition } from "@web/core/transition";
import { ErrorHandler } from "@web/core/utils/components";
import { serviceBackedItems } from "@web/ui/service_backed_items";

import { Notification } from "./notification.js";
export class NotificationContainer extends Component {
    static serviceName = "notification";
    static itemsKey = "notifications";
    /** @type {import("@odoo/owl").ComponentConstructor} */
    static notificationComponent = Notification;
    static props = { notifications: t.object().optional() };

    static template = "web.NotificationContainer";
    /** @type {Record<string, import("@odoo/owl").ComponentConstructor>} */
    static components = { ErrorHandler, Notification, Transition };
    props = useProps(this.constructor.props);

    /** @type {any} */
    notifications;

    setup() {
        /** @type {Object<string, { props: Object }>} */
        this.notifications = proxy(serviceBackedItems(this, this.props.notifications));
    }

    /**
     * @param {string} key
     * @param {Error} error
     */
    handleError(key, error) {
        this.notifications[key]?.props.close();
        reportUncaught(error);
    }
}
