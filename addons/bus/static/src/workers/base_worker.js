/** @odoo-module native */
export class BaseWorker {
    /**
     * @param {string} name
     * @param {boolean} [isShared]
     */
    constructor(name, isShared = Boolean(name?.includes("shared"))) {
        this.name = name;
        this.isShared = isShared;
        this.client = null;
    }

    handleMessage(event) {
        const { action } = event.data;
        if (action === "BASE:INIT") {
            if (this.isShared) {
                event.target.postMessage({ type: "BASE:INITIALIZED" });
            } else {
                (this.client || globalThis).postMessage({ type: "BASE:INITIALIZED" });
            }
        }
    }
}
