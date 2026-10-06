(function () {
    "use strict";

    const o = (globalThis.odoo ??= {});
    if (o.loader) {
        return;
    }

    // Safari ships no Temporal yet (coding_guidelines.rst §5.3). A parser-blocking
    // script runs before any module of the page; 'strict-dynamic' admits it only
    // with this shim's nonce.
    if (!globalThis.Temporal && globalThis.document?.readyState === "loading") {
        const nonce = document.currentScript?.nonce;
        document.write(
            `<script${nonce ? ` nonce="${nonce}"` : ""} src="/web/static/lib/temporal-polyfill/temporal-polyfill.js"></script>`,
        );
    }

    /**
     * @param {EventTarget | null} target
     * @returns {string}
     */
    function bundleAssetSrc(target) {
        const el = /** @type {any} */ (target);
        const src =
            (el?.tagName === "SCRIPT" && (el.src || el.dataset?.src)) ||
            (el?.tagName === "LINK" && el.href) ||
            "";
        // precompiled templates are optional: without them the page compiles
        // its templates itself, a reload would not bring them
        return src && src.includes("/web/assets/") && !src.includes("/web/assets/owl/")
            ? String(src)
            : "";
    }

    function _loaderDebug(...parts) {
        try {
            const o = globalThis.odoo;
            const on =
                (o && typeof o.debug === "string" && o.debug.includes("assets")) ||
                globalThis.localStorage?.getItem?.("debug.assets") ||
                globalThis.__ODOO_ASSET_TRACE__;
            if (on) {
                // eslint-disable-next-line no-console -- opt-in asset-loader trace diagnostics
                console.debug("[asset.loader]", ...parts);
            }
        } catch {}
    }

    class OdooModuleLoader {
        modules = new Map();

        bus = new EventTarget();

        /** @type {Set<string>} */
        settledBundles = new Set();

        /** @type {Map<string, Record<string, any>>} */
        externals = new Map();

        /** @type {((specifier: string) => string) | undefined} */
        resolve;

        /**
         * A page bundle served as a classic script cannot import: the module
         * script in front of it imports the libraries it needs and hands them
         * over, with the one thing only a module can do.
         *
         * @param {Record<string, any>} namespaces
         * @param {(specifier: string) => string} resolve
         */
        provideExternals(namespaces, resolve) {
            for (const [specifier, namespace] of Object.entries(namespaces)) {
                this.externals.set(specifier, namespace);
            }
            this.resolve = resolve;
        }

        /**
         * @param {string} specifier
         * @returns {Record<string, any>}
         */
        external(specifier) {
            const namespace = this.externals.get(specifier);
            if (!namespace) {
                throw new Error(
                    `the page did not provide "${specifier}" to its classic bundle`,
                );
            }
            // a bundler's interop takes this for an ES module, default export
            // included, instead of wrapping it as CommonJS
            return { ...namespace, __esModule: true };
        }

        /**
         * What a classic bundle registers for a library is the copy its
         * interop made of it. The library itself is what every other bundle
         * registers, and a copy beside it would read as a second instance.
         *
         * @param {string} name
         * @param {any} mod
         */
        _providedNamespace(name, mod) {
            const provided = this.externals.get(name);
            return provided &&
                mod &&
                Object.keys(provided).every((key) => mod[key] === provided[key])
                ? provided
                : mod;
        }

        /**
         * @param {Record<string, any>} modulesByName
         * @param {string} [bundle]
         */
        registerNativeModules(modulesByName, bundle) {
            const entries = Object.entries(modulesByName);
            _loaderDebug("registerNativeModules count=", entries.length);
            /** @type {string[] | undefined} */
            let rebound;
            for (const [name, registered] of entries) {
                const mod = this._providedNamespace(name, registered);
                const prev = this.modules.get(name);
                if (prev !== undefined && prev !== mod) {
                    (rebound ??= []).push(name);
                }
                this.modules.set(name, mod);
            }
            if (rebound) {
                _loaderDebug("registerNativeModules rebind", rebound);
                const dbg = typeof o.debug === "string" ? o.debug : "";
                if (!dbg) {
                    reportJsError({
                        kind: "module_rebind",
                        message:
                            "singleton split (module rebound): " + rebound.join(","),
                    });
                }
                try {
                    this.bus.dispatchEvent(
                        new CustomEvent("rebind", { detail: { specifiers: rebound } }),
                    );
                } catch {}
            }
            if (bundle) {
                this.settledBundles.add(bundle);
            }
            try {
                this.bus.dispatchEvent(
                    new CustomEvent("registered", {
                        detail: { specifiers: entries.map(([name]) => name), bundle },
                    }),
                );
            } catch {}
        }

        /** @returns {string[]} */
        pendingBundles() {
            const scripts =
                globalThis.document?.querySelectorAll("script[data-bridge]");
            const pending = [];
            for (const script of scripts || []) {
                const bundle = script.dataset.bridge;
                if (bundle && !this.settledBundles.has(bundle)) {
                    pending.push(bundle);
                }
            }
            return pending;
        }

        /** @param {() => void} callback */
        whenBundlesEvaluated(callback) {
            if (!this.pendingBundles().length) {
                callback();
                return;
            }
            const onSettled = () => {
                if (!this.pendingBundles().length) {
                    this.bus.removeEventListener("registered", onSettled);
                    callback();
                }
            };
            this.bus.addEventListener("registered", onSettled);
        }

        /** @param {EventTarget | null} target */
        settleFailedBundle(target) {
            const bundle = /** @type {any} */ (target)?.dataset?.bridge;
            if (!bundle || this.settledBundles.has(bundle)) {
                return;
            }
            this.settledBundles.add(bundle);
            try {
                this.bus.dispatchEvent(
                    new CustomEvent("registered", {
                        detail: { specifiers: [], bundle },
                    }),
                );
            } catch {}
        }

        /**
         * @param {EventTarget | null} target
         * @returns {boolean}
         */
        handleAssetLoadError(target) {
            const src = bundleAssetSrc(target);
            if (!src) {
                return false;
            }
            const GUARD_KEY = "odoo-asset-reload-ts";
            try {
                const storage = globalThis.sessionStorage;
                const last = parseInt(storage.getItem(GUARD_KEY) ?? "", 10) || 0;
                const now = Date.now();
                if (now - last < 60_000) {
                    return false;
                }
                storage.setItem(GUARD_KEY, String(now));
            } catch {
                return false;
            }
            _loaderDebug("asset load failed, reloading once:", src);
            this._reloadPage();
            return true;
        }

        _reloadPage() {
            globalThis.location.reload();
        }
    }

    o.loader = new OdooModuleLoader();

    const ENDPOINT = "/web/observability/js_error";
    const MAX_MESSAGE = 4096;
    const MAX_STACK = 4096;
    const MAX_CAUSE = 4096;
    const MAX_CAUSE_DEPTH = 8;
    const MAX_SEEN_KEYS = 512;

    const KINDS = new Set([
        "error",
        "unhandledrejection",
        "module_rebind",
        "service_start",
        "asset_load_error",
    ]);

    const IGNORED_MESSAGE_PREFIXES = [
        "ResizeObserver loop completed with undelivered notifications",
        "ResizeObserver loop limit exceeded",
    ];

    /**
     * @param {string} message
     * @returns {boolean}
     */
    function isIgnoredMessage(message) {
        return IGNORED_MESSAGE_PREFIXES.some((prefix) => message.startsWith(prefix));
    }

    /**
     * @param {string} str
     * @returns {string}
     */
    function hashCode(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = (hash << 5) - hash + str.charCodeAt(i);
            hash |= 0;
        }
        return (hash + 16 ** 8).toString(16).slice(-8);
    }

    /**
     * @param {string} key
     * @param {unknown} value
     * @returns {unknown}
     */
    function elideNested(key, value) {
        if (key === "") {
            return value;
        }
        return value && typeof value === "object" ? "[object]" : value;
    }

    /**
     * @param {unknown} cause
     * @returns {string}
     */
    function serializeCause(cause) {
        const parts = [];
        const visited = new Set();
        let current = cause;
        let depth = 0;
        while (current !== undefined && current !== null && depth < MAX_CAUSE_DEPTH) {
            if (typeof current === "object") {
                if (visited.has(current)) {
                    parts.push("Caused by: [circular]");
                    break;
                }
                visited.add(current);
            }
            let text;
            try {
                if (current instanceof Error) {
                    text = `${current.name}: ${current.message}`;
                } else if (typeof current === "object") {
                    text = JSON.stringify(current, elideNested);
                } else {
                    text = String(current);
                }
            } catch {
                text = "[unserializable]";
            }
            parts.push(`Caused by: ${text}`);
            current = /** @type {{ cause?: unknown }} */ (current)?.cause;
            depth++;
        }
        return parts.join("\n").slice(0, MAX_CAUSE);
    }

    const seenErrors = new Set();

    /**
     * @param {{
     * message: unknown,
     * kind?: string,
     * phase?: string,
     * filename?: string,
     * line?: number,
     * col?: number,
     * stack?: string,
     * cause?: unknown,
     * reloaded?: boolean,
     * dedup?: boolean,
     * }} info
     * @returns {boolean}
     */
    function reportJsError(info) {
        const message = String(info?.message ?? "");
        if (!message || isIgnoredMessage(message)) {
            return false;
        }
        const line = (info.line ?? 0) | 0;
        const col = (info.col ?? 0) | 0;
        const stack = info.stack ? String(info.stack).slice(0, MAX_STACK) : "";
        const cause = serializeCause(info.cause);
        if (info.dedup ?? true) {
            const key = `${message}|${line}|${col}|${hashCode(stack + cause)}`;
            if (seenErrors.has(key)) {
                return false;
            }
            if (seenErrors.size >= MAX_SEEN_KEYS) {
                seenErrors.delete(seenErrors.values().next().value);
            }
            seenErrors.add(key);
        }
        try {
            const payload = {
                phase: info.phase ?? (o.isReady ? "post_boot" : "pre_boot"),
                kind: KINDS.has(info.kind) ? info.kind : "error",
                message: message.slice(0, MAX_MESSAGE),
                cause,
                filename: String(info.filename ?? ""),
                line,
                col,
                stack,
                url: globalThis.location?.href || "",
                user_agent: globalThis.navigator?.userAgent || "",
            };
            if (info.reloaded !== undefined) {
                payload.reloaded = info.reloaded;
            }
            const blob = new Blob([JSON.stringify(payload)], {
                type: "application/json",
            });
            return Boolean(globalThis.navigator?.sendBeacon?.(ENDPOINT, blob));
        } catch {
            return false;
        }
    }

    o.loader._beacon = {
        reportJsError,
        seenErrors,
        serializeCause,
        hashCode,
        limits: {
            ENDPOINT,
            MAX_MESSAGE,
            MAX_STACK,
            MAX_CAUSE,
            MAX_CAUSE_DEPTH,
            MAX_SEEN_KEYS,
            KINDS,
        },
    };

    globalThis.addEventListener?.("error", (ev) => {
        if (globalThis.odoo?.isReady) {
            return;
        }
        reportJsError({
            phase: "pre_boot",
            kind: "error",
            message: ev.message || ev.error?.message || "(no message)",
            cause: ev.error?.cause,
            filename: ev.filename,
            line: ev.lineno,
            col: ev.colno,
            stack: ev.error?.stack,
        });
    });
    globalThis.addEventListener?.(
        "error",
        (ev) => {
            const target = ev.target;
            if (!target || target === globalThis) {
                return;
            }
            const src = bundleAssetSrc(target);
            if (!src) {
                return;
            }
            o.loader.settleFailedBundle(target);
            const reloaded = o.loader.handleAssetLoadError(target);
            reportJsError({
                kind: "asset_load_error",
                message: reloaded
                    ? "bundle asset failed to load; reloading once"
                    : "bundle asset failed to load; reload suppressed",
                reloaded,
                filename: src,
            });
        },
        true,
    );
    globalThis.addEventListener?.("unhandledrejection", (ev) => {
        if (globalThis.odoo?.isReady) {
            return;
        }
        const reason = ev.reason;
        const message =
            reason instanceof Error
                ? reason.message
                : typeof reason === "string"
                  ? reason
                  : "(non-error rejection)";
        reportJsError({
            phase: "pre_boot",
            kind: "unhandledrejection",
            message,
            cause: /** @type {{ cause?: unknown }} */ (reason)?.cause,
            stack: reason instanceof Error ? reason.stack : "",
        });
    });
})();
