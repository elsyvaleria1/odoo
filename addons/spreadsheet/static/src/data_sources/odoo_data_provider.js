/** @odoo-module native */
import { EventBus } from "@odoo/owl";

import { ServerData } from "./server_data.js";

export class OdooDataProvider extends EventBus {
    constructor(env) {
        super();
        this.orm = env.services.orm;
        this.fieldService = env.services.field;
        this.serverData = new ServerData(this.orm, {
            whenDataStartLoading: (promise) => this.notifyWhenPromiseResolves(promise),
        });
        this.pendingPromises = new Set();
    }

    cancelPromise(promise) {
        this.pendingPromises.delete(promise);
    }

    /**
     * @param {Promise<unknown>} promise
     */
    async notifyWhenPromiseResolves(promise) {
        this.pendingPromises.add(promise);
        await promise
            .then(() => {
                this.pendingPromises.delete(promise);
                this.notify();
            })
            .catch(() => {
                this.pendingPromises.delete(promise);
                this.notify();
            });
    }

    notify() {
        if (this.pendingPromises.size) {
            if (!this.nextTriggerTimeOutId) {
                this.nextTriggerTimeOutId = setTimeout(() => {
                    this.nextTriggerTimeOutId = undefined;
                    if (this.pendingPromises.size) {
                        this.trigger("data-source-updated");
                    }
                }, 10000);
            }
            return;
        }
        this.trigger("data-source-updated");
    }
}
