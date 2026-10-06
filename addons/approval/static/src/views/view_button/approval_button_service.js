/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

import { trace } from "../../common/approval_trace.js";

/**
 * Collects the specs asked in one tick and answers them with one call, so a form
 * with several gated buttons costs one round trip.
 *
 * It also owns the refresh of those buttons when their record reloads. A model
 * gets one lifecycle listener, not one per button: the model awaits its
 * listeners one after the other, so a listener per button turned a pager step
 * into as many sequential round trips as the form has gated buttons, and held
 * the pager disabled until the last one answered.
 */
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
                        // Every queued button fails open on this, so it is the one
                        // place that knows the gates were never actually consulted.
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
         * Reloads every gate of `model` whenever its root loads or a record saves.
         *
         * The reload is not handed back to the model: approvals are side data the
         * record renders without, and the server gates every call anyway, so a
         * load -- and the pager driving it -- must not wait for them. All gates
         * ask in the same tick, which `load` answers with one call.
         *
         * @param {object} model a RelationalModel
         * @param {TrackedGate} gate
         * @returns {() => void} stops tracking the gate
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
