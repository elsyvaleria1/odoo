/** @odoo-module native */
import { pageServerURL } from "@bus/bus_parameters_service";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Deferred } from "@web/core/utils/concurrency";
import { session } from "@web/session";

export const WORKER_STATE = Object.freeze({
    UNINITIALIZED: "UNINITIALIZED",
    INITIALIZING: "INITIALIZING",
    INITIALIZED: "INITIALIZED",
    FAILED: "FAILED",
});

export class WorkerService {
    constructor(env, services) {
        this.params = services["bus.parameters"];
        this.worker = null;
        this.isUsingSharedWorker = Boolean(browser.SharedWorker);
        this._state = WORKER_STATE.UNINITIALIZED;
        this._failureWarned = false;
        this.connectionInitializedDeferred = new Deferred();
    }

    /** @returns {"shared" | "dedicated" | "failed" | null} */
    get workerKind() {
        if (this._state === WORKER_STATE.FAILED) {
            return "failed";
        }
        if (this._state !== WORKER_STATE.INITIALIZED) {
            return null;
        }
        return this.isUsingSharedWorker ? "shared" : "dedicated";
    }

    async startWorker() {
        this._state = WORKER_STATE.INITIALIZING;
        const ownServer = this.params.serverURL === pageServerURL();
        const version = session.websocket_worker_version;
        let workerURL = `${window.origin}/bus/websocket_worker_bundle?v=${version}`;
        let blobURL = null;
        if (!ownServer) {
            try {
                const response = await fetch(
                    `${this.params.serverURL}/bus/websocket_worker_bundle/anonymous?v=${version}`,
                    { credentials: "omit" },
                );
                if (!response.ok) {
                    throw new Error(
                        `Bundle fetch failed with status ${response.status}`,
                    );
                }
                const text = await response.text();
                blobURL = URL.createObjectURL(
                    new Blob([text], { type: "application/javascript" }),
                );
                workerURL = blobURL;
            } catch (e) {
                this._state = WORKER_STATE.FAILED;
                this.connectionInitializedDeferred.resolve();
                console.warn(
                    "Worker service failed to initialize: could not fetch worker bundle.",
                    e,
                );
                return;
            }
        }
        const workerClass = this.isUsingSharedWorker
            ? browser.SharedWorker
            : browser.Worker;
        try {
            this.worker = new workerClass(workerURL, {
                name: this.isUsingSharedWorker
                    ? "odoo:bus_shared_worker"
                    : "odoo:bus_worker",
                type: "module",
            });
        } catch (e) {
            this.onInitError(e);
            return;
        } finally {
            if (blobURL) {
                URL.revokeObjectURL(blobURL);
            }
        }
        const worker = this.worker;
        worker.onerror = (e) => {
            if (worker === this.worker) {
                this.onInitError(e);
            }
        };
        this._registerHandler((ev) => {
            if (ev.data.type === "BASE:INITIALIZED") {
                this._state = WORKER_STATE.INITIALIZED;
                this.connectionInitializedDeferred.resolve();
            } else if (ev.data.type === "BUS:PING") {
                this._send("BUS:PONG");
            }
        });
        if (this.isUsingSharedWorker) {
            this.worker.port.start();
        }
        this._send("BASE:INIT");
    }

    async ensureWorkerStarted() {
        if (this._state === WORKER_STATE.UNINITIALIZED) {
            this.startWorker();
        }
        await this.connectionInitializedDeferred;
    }

    onInitError(e) {
        if (this._state === WORKER_STATE.INITIALIZING && this.isUsingSharedWorker) {
            console.warn("Error while loading SharedWorker, fallback on Worker: ", e);
            this.isUsingSharedWorker = false;
            this.worker?.port?.close?.();
            this.startWorker();
        } else if (this._state === WORKER_STATE.INITIALIZING) {
            this._state = WORKER_STATE.FAILED;
            this.connectionInitializedDeferred.resolve();
            console.warn("Worker service failed to initialize: ", e);
        } else {
            this._state = WORKER_STATE.FAILED;
            console.warn("Worker crashed after initialization: ", e);
        }
    }

    _registerHandler(handler) {
        if (this.isUsingSharedWorker) {
            this.worker.port.addEventListener("message", handler);
        } else {
            this.worker.addEventListener("message", handler);
        }
    }

    _send(action, data) {
        const message = { action, data };
        if (this.isUsingSharedWorker) {
            this.worker.port.postMessage(message);
        } else {
            this.worker.postMessage(message);
        }
    }

    /**
     * @param {String} action
     * @param {Object|undefined} data
     */
    async send(action, data) {
        if (this._state === WORKER_STATE.UNINITIALIZED) {
            return;
        }
        await this.connectionInitializedDeferred;
        if (this._state === WORKER_STATE.FAILED) {
            this._warnFailedOnce();
            return;
        }
        this._send(action, data);
    }

    /** @param {function} handler */
    async registerHandler(handler) {
        if (this._state === WORKER_STATE.UNINITIALIZED) {
            this.startWorker();
        }
        await this.connectionInitializedDeferred;
        if (this._state === WORKER_STATE.FAILED) {
            this._warnFailedOnce();
            return;
        }
        this._registerHandler(handler);
    }

    _warnFailedOnce() {
        if (this._failureWarned) {
            return;
        }
        this._failureWarned = true;
        console.warn(
            "Worker service failed to initialize: worker messages are dropped" +
                " (this warning is only shown once).",
        );
    }

    get state() {
        return this._state;
    }
}

export const workerService = {
    dependencies: ["bus.parameters"],
    start(env, services) {
        return new WorkerService(env, services);
    },
};

registry.category("services").add("worker_service", workerService);
