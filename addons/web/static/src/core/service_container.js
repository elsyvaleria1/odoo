// @ts-check
/** @odoo-module native */
import { t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { reportJsError } from "@web/core/errors/error_beacon";
import { AppEvent } from "@web/core/events";
import { registry } from "@web/core/registry";
import { makeAssetLog, serviceLog } from "@web/core/utils/asset_log";
import {
    deferUntilBundlesSettled,
    whenBundlesSettled,
} from "@web/core/utils/bundle_transaction";
import {
    createWaveResolver,
    findDependencyCycle,
} from "@web/core/utils/dependency_graph";
import { SERVICES_METADATA } from "@web/core/utils/hooks";

const log = makeAssetLog("env");
const debugLog = makeLogger("web.env");

/**
 * @typedef {{
 * bus: import("@odoo/owl").EventBus;
 * debug: string;
 * services: import("services").ServiceFactories;
 * readonly isSmall: boolean;
 * [key: string]: any;
 * }} ServiceContext
 */

const serviceRegistry = registry.category("services");

serviceRegistry.addValidation(
    t.object({
        start: t.function(),
        dependencies: t.array(t.string()).optional(),
        async: t.or([t.array(t.string()), t.literal(true)]).optional(),
    }),
);

/** @type {Set<string>} */
const _seenCascadeWarnings = new Set();

/** @type {Set<string>} */
const _reportedDependencies = new Set();

export function _resetCascadeWarningCache() {
    _seenCascadeWarnings.clear();
    _reportedDependencies.clear();
}

/**
 * @param {Record<string, any>} services
 * @returns {Map<string, string[]>}
 */
function findUnregisteredDependencies(services) {
    /** @type {Map<string, string[]>} */
    const missing = new Map();
    for (const [name, service] of serviceRegistry.getEntries()) {
        if (name in services) {
            continue;
        }
        const unregistered = (service.dependencies || []).filter(
            (/** @type {string} */ dep) =>
                !(dep in services) && !serviceRegistry.contains(dep),
        );
        if (unregistered.length) {
            missing.set(name, unregistered);
        }
    }
    return missing;
}

/**
 * @param {Record<string, any>} services
 * @param {Iterable<string>} roots
 * @returns {string[]}
 */
function blockedBy(services, roots) {
    const blocked = new Set(roots);
    let changed = true;
    while (changed) {
        changed = false;
        for (const [name, service] of serviceRegistry.getEntries()) {
            if (
                !(name in services) &&
                !blocked.has(name) &&
                (service.dependencies || []).some((/** @type {string} */ dep) =>
                    blocked.has(dep),
                )
            ) {
                blocked.add(name);
                changed = true;
            }
        }
    }
    for (const root of roots) {
        blocked.delete(root);
    }
    return [...blocked].sort();
}

export class ServiceContainer {
    /** @type {Promise<void> | null} */
    _pending = null;
    /** @type {(() => void) | null} */
    _stopListening = null;
    /** @type {Set<string>} */
    _failed = new Set();
    _destroyed = false;

    /** @param {ServiceContext} context */
    constructor(context) {
        this.context = context;
        this.services = context.services;
    }

    async start() {
        log("startServices: registry size=", serviceRegistry.getEntries().length);
        await Promise.resolve();

        const runStartupPass = async () => {
            try {
                await this._start(new Map());
            } catch (error) {
                console.error(
                    "[env] service startup pass (registry UPDATE) failed:",
                    error,
                );
            }
            this.checkDependencies();
        };
        /** @param {any} ev */
        const onRegistryUpdate = async (ev) => {
            await Promise.resolve();
            const { operation } = ev.detail;
            if (operation === "delete") {
                return;
            }
            if (deferUntilBundlesSettled(runStartupPass)) {
                return;
            }
            await runStartupPass();
        };
        this.stopListening();
        serviceRegistry.addEventListener("UPDATE", onRegistryUpdate);
        this._stopListening = () => {
            serviceRegistry.removeEventListener("UPDATE", onRegistryUpdate);
        };
        await this._start(new Map());
        this.checkDependencies();
    }

    async startMissing() {
        await Promise.resolve();
        await this._start(new Map());
        this.checkDependencies();
    }

    checkDependencies() {
        whenBundlesSettled(() => this._reportUnregisteredDependencies());
    }

    _reportUnregisteredDependencies() {
        if (this._destroyed) {
            return;
        }
        const missing = findUnregisteredDependencies(this.services);
        const lines = [];
        for (const [name, dependencies] of missing) {
            const key = `${name}|${dependencies.join(",")}`;
            if (_reportedDependencies.has(key)) {
                continue;
            }
            _reportedDependencies.add(key);
            const blocked = blockedBy(this.services, [name]);
            const message =
                `service "${name}" is not started: no module registers its ` +
                `dependenc${dependencies.length > 1 ? "ies" : "y"} ` +
                dependencies.map((dep) => `"${dep}"`).join(", ") +
                (blocked.length
                    ? `; nor are its dependents ${blocked.join(", ")}`
                    : "");
            lines.push(message);
            reportJsError({ kind: "service_start", message });
        }
        if (lines.length) {
            console.warn(`[env] ${lines.join("\n[env] ")}`);
        }
    }

    stopListening() {
        this._stopListening?.();
        this._stopListening = null;
    }

    destroy() {
        this._destroyed = true;
        this.stopListening();
        for (const [name, service] of Object.entries(this.services)) {
            try {
                /** @type {any} */ (service)?.destroy?.();
            } catch (error) {
                console.error(`[env] service "${name}" destroy() failed:`, error);
            }
        }
    }

    /**
     * @param {string} name
     * @param {"sync" | "async"} mode
     * @param {unknown} error
     */
    _reportFailure(name, mode, error) {
        console.error(`[env] service "${name}" failed to start (${mode}):`, error);
        serviceLog("failed", name, mode);
        reportJsError({
            kind: "service_start",
            message: `service "${name}" failed to start (${mode})`,
            stack: /** @type {any} */ (error)?.stack
                ? String(/** @type {any} */ (error).stack)
                : "",
            cause: error,
        });
    }

    /**
     * @param {string} name
     * @param {Set<string>} seen
     * @returns {Set<string>}
     */
    _failedRoots(name, seen) {
        const roots = new Set();
        const service = serviceRegistry.contains(name)
            ? serviceRegistry.get(name)
            : null;
        for (const dep of service?.dependencies || []) {
            if (this._failed.has(dep)) {
                roots.add(dep);
            } else if (
                !(dep in this.services) &&
                serviceRegistry.contains(dep) &&
                !seen.has(dep)
            ) {
                seen.add(dep);
                for (const root of this._failedRoots(dep, seen)) {
                    roots.add(root);
                }
            }
        }
        return roots;
    }

    /** @param {string[]} skipped */
    _warnFailedDependencies(skipped) {
        const blocked = [];
        const causes = new Set();
        for (const name of skipped) {
            const roots = this._failedRoots(name, new Set());
            if (roots.size) {
                blocked.push(name);
                for (const root of roots) {
                    causes.add(root);
                }
            }
        }
        if (!blocked.length) {
            return;
        }
        blocked.sort();
        const failedNames = [...causes].sort();
        const dedupKey = `${blocked.join(",")}|${failedNames.join(",")}`;
        if (_seenCascadeWarnings.has(dedupKey)) {
            return;
        }
        _seenCascadeWarnings.add(dedupKey);
        console.warn(
            `[env] Skipped ${blocked.length} service(s) whose dependency failed ` +
                `to start: ${blocked.join(", ")}. Failed: ${failedNames.join(", ")}.`,
        );
    }

    /** @param {Map<string, any>} toStart */
    async _start(toStart) {
        if (this._pending) {
            return this._pending.catch(() => {}).then(() => this._start(toStart));
        }
        const { context, services, _failed: failed } = this;
        for (const [name, service] of serviceRegistry.getEntries()) {
            if (!(name in services)) {
                const namedService = Object.assign(Object.create(service), {
                    name,
                });
                toStart.set(name, namedService);
            }
        }

        const resolver = createWaveResolver({
            isLoaded: (dep) => dep in services,
        });

        /** @param {string} name */
        function _trackService(name) {
            const service = toStart.get(name);
            if (!service) {
                return;
            }
            resolver.track(name, service.dependencies || []);
        }

        for (const name of toStart.keys()) {
            _trackService(name);
        }

        let _wave = 0;
        /**
         * @param {string} name
         * @param {"sync" | "async"} mode
         * @param {unknown} error
         */
        const _reportServiceFailure = (name, mode, error) => {
            failed.add(name);
            this._reportFailure(name, mode, error);
        };

        async function start() {
            for (const name of toStart.keys()) {
                _trackService(name);
            }

            const proms = [];
            const waveStarted = [];
            while (resolver.hasReady()) {
                const name = /** @type {string} */ (resolver.shift());
                if (name in services) {
                    continue;
                }
                const service = toStart.get(name);
                if (!service) {
                    continue;
                }
                toStart.delete(name);
                resolver.untrack(name);
                const entries = (service.dependencies || []).map((dep) => [
                    dep,
                    services[dep],
                ]);
                const dependencies = Object.fromEntries(entries);
                let value;
                const endStart = debugLog.perf(`service ${name}`);
                try {
                    value = service.start(context, dependencies);
                } catch (error) {
                    _reportServiceFailure(name, "sync", error);
                    continue;
                }
                if ("async" in service) {
                    SERVICES_METADATA[name] = service.async;
                }
                waveStarted.push(name);
                serviceLog("start", name, service.dependencies || []);
                proms.push(
                    Promise.resolve(value).then(
                        (val) => {
                            services[name] = val ?? null;
                            failed.delete(name);
                            endStart({ dependencies: service.dependencies || [] });
                            serviceLog("started", name);
                            resolver.propagate(name);
                        },
                        (error) => {
                            endStart({ failed: true });
                            _reportServiceFailure(name, "async", error);
                        },
                    ),
                );
            }
            if (waveStarted.length) {
                debugLog.pipeline("services wave", () => ({
                    wave: _wave + 1,
                    started: waveStarted,
                }));
                log(
                    `services wave ${++_wave} started (${waveStarted.length}):`,
                    waveStarted,
                );
            }
            await Promise.all(proms);
            if (proms.length) {
                return start();
            }
        }
        this._pending = start().finally(() => {
            this._pending = null;
        });
        await this._pending;
        if (toStart.size) {
            const skipped = [];
            let changed = true;
            while (changed) {
                changed = false;
                for (const [name, service] of toStart) {
                    const hasMissingDep = (service.dependencies || []).some(
                        (/** @type {string} */ dep) =>
                            !(dep in services) && !toStart.has(dep),
                    );
                    if (hasMissingDep) {
                        toStart.delete(name);
                        skipped.push(name);
                        changed = true;
                    }
                }
            }
            this._warnFailedDependencies(skipped);
            if (toStart.size) {
                const depGraph = new Map();
                for (const [name, service] of toStart) {
                    depGraph.set(name, service.dependencies || []);
                }
                const cycle = findDependencyCycle(depGraph);
                if (cycle) {
                    throw new Error(
                        `Circular service dependency detected: ${cycle.join(" \u2192 ")}`,
                    );
                }
                console.warn(
                    `[env] ${toStart.size} service(s) left unstarted with no ` +
                        `dependency cycle: ${[...toStart.keys()].join(", ")}. ` +
                        `A registry update raced this startup pass; the next ` +
                        `startServices/startMissingServices pass will start them.`,
                );
            }
        }
        log(
            "startServices: done — started=",
            Object.keys(services).length,
            "waves=",
            _wave,
        );
        context.bus.trigger(AppEvent.SERVICES_LOADED);
    }
}
