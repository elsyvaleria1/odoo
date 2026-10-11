/** @odoo-module native */
import { EventBus } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Deferred } from "@web/core/utils/concurrency";
import { session } from "@web/session";

const MAIN_TAB_LOCK = "odoo.bus.main_tab";
const FRONTEND_MAIN_LOCK = "odoo.bus.main_tab.frontend";
const BACKEND_TAB_LOCK = "odoo.bus.main_tab.backend";

export const multiTabService = {
    start() {
        const bus = new EventBus();
        const locks = browser.navigator?.locks;
        let isMain = false;
        let terminated = false;
        let settled = new Deferred();
        let releaseHeld = null;
        let grant = null;
        let releaseSide = null;
        let abortController = null;
        let attempt = 0;
        const isFrontend = Boolean(session.is_frontend);

        function isCurrent(myAttempt) {
            return !terminated && myAttempt === attempt;
        }

        async function isHeld(name) {
            try {
                const { held } = await locks.query();
                return held.some((lock) => lock.name === name);
            } catch {
                return false;
            }
        }

        function holdSide(name, options, myAttempt) {
            return new Promise((resolve, reject) => {
                locks
                    .request(name, options, () => {
                        const held = new Deferred();
                        const release = () => held.resolve();
                        if (isCurrent(myAttempt)) {
                            releaseSide = release;
                        } else {
                            release();
                        }
                        resolve();
                        return held;
                    })
                    .catch(reject);
            });
        }

        function dropSide() {
            releaseSide?.();
            releaseSide = null;
        }

        async function holdMain(myAttempt) {
            if (!isCurrent(myAttempt)) {
                return;
            }
            const myGrant = (grant = { lost: false });
            if (isFrontend) {
                let yieldToBackend = true;
                try {
                    await holdSide(FRONTEND_MAIN_LOCK, {}, myAttempt);
                    yieldToBackend = await isHeld(BACKEND_TAB_LOCK);
                } catch (error) {
                    if (error?.name !== "AbortError") {
                        yieldToBackend = false;
                    }
                }
                if (myGrant.lost || !isCurrent(myAttempt)) {
                    return;
                }
                if (yieldToBackend) {
                    dropSide();
                    grant = null;
                    queueMain(myAttempt);
                    return;
                }
            }
            isMain = true;
            settled.resolve();
            bus.trigger("become_main_tab");
            const held = new Deferred();
            releaseHeld = () => held.resolve();
            return held;
        }

        function onMainLockError(error, myAttempt) {
            if (error?.name !== "AbortError") {
                console.warn("Main-tab lock refused; this tab acts as main:", error);
                dropSide();
                becomeMainWithoutLocks();
                return;
            }
            if (!grant || !isCurrent(myAttempt)) {
                return;
            }
            grant.lost = true;
            grant = null;
            releaseHeld = null;
            if (isFrontend) {
                dropSide();
            }
            if (isMain) {
                isMain = false;
                bus.trigger("no_longer_main_tab");
            }
            queueMain(myAttempt);
        }

        async function queueMain(myAttempt) {
            settled.resolve();
            const steal = !isFrontend && (await isHeld(FRONTEND_MAIN_LOCK));
            if (!isCurrent(myAttempt)) {
                return;
            }
            locks
                .request(
                    MAIN_TAB_LOCK,
                    steal ? { steal } : { signal: abortController.signal },
                    () => holdMain(myAttempt),
                )
                .catch((error) => onMainLockError(error, myAttempt));
        }

        function becomeMainWithoutLocks() {
            if (!isMain && !terminated) {
                isMain = true;
                bus.trigger("become_main_tab");
            }
            settled.resolve();
        }

        async function acquire() {
            if (terminated) {
                settled.resolve();
                return;
            }
            if (!locks) {
                becomeMainWithoutLocks();
                return;
            }
            const myAttempt = ++attempt;
            abortController = new AbortController();
            const { signal } = abortController;
            if (!isFrontend) {
                try {
                    await holdSide(
                        BACKEND_TAB_LOCK,
                        { mode: "shared", signal },
                        myAttempt,
                    );
                } catch (error) {
                    if (error?.name !== "AbortError") {
                        onMainLockError(error, myAttempt);
                    }
                    return;
                }
                if (!isCurrent(myAttempt)) {
                    return;
                }
            }
            locks
                .request(MAIN_TAB_LOCK, { ifAvailable: true }, (lock) => {
                    if (lock) {
                        return holdMain(myAttempt);
                    }
                    if (isCurrent(myAttempt)) {
                        queueMain(myAttempt);
                    }
                })
                .catch((error) => onMainLockError(error, myAttempt));
        }

        function deactivate() {
            if (isMain) {
                isMain = false;
                bus.trigger("no_longer_main_tab");
            }
            attempt++;
            settled.resolve();
            releaseHeld?.();
            releaseHeld = null;
            grant = null;
            dropSide();
            abortController?.abort();
            abortController = null;
        }

        browser.addEventListener("pagehide", deactivate);
        browser.addEventListener("pageshow", (ev) => {
            if (ev.persisted && !terminated) {
                settled = new Deferred();
                acquire();
            }
        });

        acquire();

        return {
            bus,
            async isOnMainTab() {
                if (terminated) {
                    return false;
                }
                await settled;
                return isMain;
            },
            unregister() {
                terminated = true;
                deactivate();
                settled.resolve();
            },
        };
    },
};

registry.category("services").add("multi_tab", multiTabService);
