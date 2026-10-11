/** @odoo-module native */
/* eslint-disable no-console -- dedicated bus debug-logging service; console is its output */
import { proxy } from "@odoo/owl";
import { formatValue, now } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";

/**
 * Turn a BUS:PROVIDE_LOGS worker answer into a JSON file download. Lives
 * here — not in bus_service — because log collection is this service's
 * feature: the transport layer has no business doing DOM/Blob work.
 *
 * @param {MessageEvent} messageEv
 */
function handleProvideLogs(messageEv) {
    const { type, data } = messageEv.data;
    if (type !== "BUS:PROVIDE_LOGS") {
        return;
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bus_logs_${formatValue(now(), "yyyy-LL-dd-HH-mm-ss")}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

export const busLogsService = {
    dependencies: ["bus_service", "shared_storage", "worker_service"],
    /**
     * @param {import("@web/env").OdooEnv}
     * @param {Partial<import("services").Services>} services
     */
    start(env, { bus_service, shared_storage, worker_service }) {
        const state = proxy({
            enabled: shared_storage.getSharedValue("bus_log_menu.enabled", false),
            toggleLogging() {
                state.enabled = !state.enabled;
                bus_service.setLoggingEnabled(state.enabled);
                shared_storage.setSharedValue("bus_log_menu.enabled", state.enabled);
            },
        });
        shared_storage.bus.addEventListener("shared_value_updated", ({ detail }) => {
            if (detail.key === "bus_log_menu.enabled") {
                state.enabled = JSON.parse(detail.newValue);
                bus_service.setLoggingEnabled(state.enabled);
            }
        });
        worker_service.connectionInitializedDeferred.then(() => {
            worker_service.registerHandler(handleProvideLogs);
            bus_service.setLoggingEnabled(state.enabled);
        });
        odoo.busLogging = {
            stop: () => state.enabled && state.toggleLogging(),
            start: () => !state.enabled && state.toggleLogging(),
            download: () => bus_service.downloadLogs(),
        };
        if (state.enabled) {
            console.log(
                "Bus logging is enabled. To disable it, use `odoo.busLogging.stop()`. To download the logs, use `odoo.busLogging.download()`.",
            );
        }
        return state;
    },
};

registry.category("services").add("bus.logs_service", busLogsService);
