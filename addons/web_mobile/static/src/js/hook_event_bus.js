/** @odoo-module native */
import { EventBus } from "@odoo/owl";

export class HookEventBus extends EventBus {
    /**
     * @param {Object} hooks
     * @param {Function} [hooks.onAddListener]
     * @param {Function} [hooks.onRemoveListener]
     */
    constructor(hooks = {}) {
        super();
        this.hooks = hooks;
    }

    addEventListener(eventName, listener) {
        super.addEventListener(eventName, listener);
        this.hooks.onAddListener?.(eventName, listener);
    }

    removeEventListener(eventName, listener) {
        super.removeEventListener(eventName, listener);
        this.hooks.onRemoveListener?.(eventName, listener);
    }
}
