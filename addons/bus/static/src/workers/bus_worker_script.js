/** @odoo-module native */
/* eslint-disable no-restricted-globals */

import { BaseWorker } from "./base_worker.js";
import { WebsocketWorker } from "./websocket_worker.js";

(function () {
    const isShared = self.name.includes("shared");
    const baseWorker = new BaseWorker(self.name, isShared);
    const websocketWorker = new WebsocketWorker(self.name);

    if (isShared) {
        self.onconnect = (ev) => {
            const client = ev.ports[0];
            client.addEventListener("message", (ev) => baseWorker.handleMessage(ev));
            websocketWorker.registerClient(client);
            client.start();
        };
    } else {
        self.addEventListener("message", (ev) => baseWorker.handleMessage(ev));
        self.addEventListener("error", (ev) => {
            ev.preventDefault();
            console.error(ev.error ?? ev.message);
        });
        websocketWorker.registerClient(self);
    }
})();
