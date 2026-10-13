/** @odoo-module native */
import { registry } from "@web/core/registry";
import { session } from "@web/session";

/** @returns {string} */
export function pageServerURL() {
    if (!session.websocket_gevent_port) {
        return window.origin;
    }
    const url = new URL(window.origin);
    url.port = session.websocket_gevent_port;
    return url.origin;
}

export const busParametersService = {
    start() {
        return { serverURL: pageServerURL() };
    },
};

registry.category("services").add("bus.parameters", busParametersService);
