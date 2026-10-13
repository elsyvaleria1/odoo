/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

import { trace } from "../../common/approval_trace.js";

export const approvalButtonService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        let queue = [];
        /**
         * @typedef {{ onRootLoaded: (root: any) => any, onRecordSaved: () => any }} TrackedGate
         * @type {WeakMap<object, { gates: Set<TrackedGate>, dispose: () => void }>}
         */
        const trackedModels = new WeakMap();

        function flush() {
            const batch = queue;
            queue = [];
            const started = browser.performance.now();
            orm.silent
                .call("approval.binding", "get_button_approvals", [
                    batch.map(({ spec }) => spec),
                ])
                .then(
                    (results) => {
                        trace.event("service", "flushed", {
                            specs: batch.length,
                            ms: browser.performance.now() - started,
                            results: results.length,
                        });
                        batch.forEach(({ resolve }, index) => resolve(results[index]));
                    },
                    (error) => {
                        trace.note("service", "flush_rejected", {
                            specs: batch.length,
                            ms: browser.performance.now() - started,
                            error: error?.name || "Error",
                        });
                        batch.forEach(({ reject }) => reject(error));
                    },
                );
        }

        function load(spec) {
            return new Promise((resolve, reject) => {
                if (!queue.length) {
                    Promise.resolve().then(flush);
                }
                queue.push({ spec, resolve, reject });
            });
        }

        /**
         * @param {object} model
         * @param {TrackedGate} gate
         * @returns {() => void}
         */
        function track(model, gate) {
            let tracked = trackedModels.get(model);
            if (!tracked) {
                const gates = new Set();
                const reloadOn =
                    (on) =>
                    (...args) => {
                        trace.event("button", "reload", { on, gates: gates.size });
                        for (const trackedGate of gates) {
                            trackedGate[on](...args);
                        }
                    };
                const unsubscribe = [
                    model.subscribeLifecycle("onRootLoaded", reloadOn("onRootLoaded")),
                    model.subscribeLifecycle(
                        "onRecordSaved",
                        reloadOn("onRecordSaved"),
                    ),
                ];
                tracked = {
                    gates,
                    dispose: () => unsubscribe.forEach((dispose) => dispose()),
                };
                trackedModels.set(model, tracked);
            }
            tracked.gates.add(gate);
            return () => {
                tracked.gates.delete(gate);
                if (!tracked.gates.size) {
                    tracked.dispose();
                    trackedModels.delete(model);
                }
            };
        }

        return { load, track };
    },
};

registry.category("services").add("approval_button", approvalButtonService);
