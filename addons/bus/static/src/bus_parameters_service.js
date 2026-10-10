/** @odoo-module native */
import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * The bus of the server this page comes from. In prefork mode without a
 * reverse proxy the server exposes the gevent port so the client connects to
 * the EventServer (port 8072) instead of the HTTP prefork workers, which
 * cannot serve WebSocket.
 *
 * @returns {string}
 */
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
