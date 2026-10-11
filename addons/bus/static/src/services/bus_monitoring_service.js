/** @odoo-module native */
import { WORKER_STATE } from "@bus/services/worker_service";
import { CONNECTION_STATE } from "@bus/workers/websocket_worker_constants";
import { proxy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
export class BusMonitoringService {
    isConnectionLost = false;
    isReconnecting = false;

    constructor(env, services) {
        const reactiveThis = proxy(this);
        reactiveThis.setup(env, services);
        return reactiveThis;
    }

    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {Partial<import("services").Services>} services
     */
    setup(env, { bus_service, worker_service }) {
        bus_service.addEventListener("BUS:WORKER_STATE_UPDATED", ({ detail }) =>
            this.workerStateOnChange(detail),
        );
        browser.addEventListener("offline", () => (this.isReconnecting = false));
        worker_service.connectionInitializedDeferred.then(() => {
            if (worker_service.state === WORKER_STATE.FAILED) {
                this.isConnectionLost = true;
                this.isReconnecting = false;
            }
        });
    }

    /**
     * Handle connection-state changes of the WebSocket worker.
     *
     * @param {CONNECTION_STATE[keyof CONNECTION_STATE]} state
     */
    workerStateOnChange(state) {
        switch (state) {
            case CONNECTION_STATE.CONNECTING: {
                this.isReconnecting = true;
                break;
            }
            case CONNECTION_STATE.CONNECTED: {
                this.isReconnecting = false;
                this.isConnectionLost = false;
                break;
            }
            case CONNECTION_STATE.DISCONNECTED: {
                if (this.isReconnecting) {
                    this.isConnectionLost = true;
                    this.isReconnecting = false;
                }
                break;
            }
        }
    }
}

export const busMonitoringservice = {
    dependencies: ["bus_service", "worker_service"],
    start(env, services) {
        return new BusMonitoringService(env, services);
    },
};

registry.category("services").add("bus.monitoring_service", busMonitoringservice);
