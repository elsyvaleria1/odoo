/** @odoo-module native */
import { EventBus } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Deferred } from "@web/core/utils/concurrency";
import { session } from "@web/session";

/**
 * Main-tab election over the Web Locks API.
 *
 * A single exclusive lock arbitrates the one "main tab" of an origin: whichever
 * tab holds it is main, and when it releases the lock (tab closed, `pagehide`,
 * or `unregister()`) the browser hands it to the next waiter, which becomes
 * main. The browser does the arbitration, race-free, with no heartbeats.
 *
 * This replaces the previous three-part design — a `SharedWorker` `ElectionWorker`
 * (strategy A), a localStorage heartbeat election (strategy B), and a facade
 * that picked between them at runtime based on the effective worker kind. That
 * split had a real failure mode: when one tab's `SharedWorker` construction
 * failed and it fell back to the localStorage strategy while its siblings used
 * the worker strategy, two tabs could each believe they were main (duplicate
 * notifications/sounds/ringing). One lock removes that split-brain and behaves
 * identically for shared, dedicated, and failed workers, so `multi_tab` no
 * longer depends on `worker_service` at all.
 *
 * Public API (unchanged — consumers: mail out_of_focus / discuss_core_web / rtc,
 * survey form, voip user_agent, bus outdated_page_watcher / bus_service):
 * - `isOnMainTab(): Promise<boolean>`
 * - `unregister(): void` — terminal: the tab permanently gives up main-tab duties.
 * - `bus`: EventBus emitting "become_main_tab" / "no_longer_main_tab".
 */
// One main tab for both sides: what a website tab can do (sounds, native
// notifications, ringing) would otherwise be done twice. A backend tab does
// all of it, the backend-only duties too, so a website tab never keeps the
// lock from one. Two side locks make the hand-over race-free whichever comes
// first: a website tab that is main holds FRONTEND_MAIN_LOCK, and a backend
// tab finding it held takes the main lock over (`steal`); every backend tab
// holds BACKEND_TAB_LOCK (shared), and a website tab finding it held once it
// got the main lock gives it back.
const MAIN_TAB_LOCK = "odoo.bus.main_tab";
const FRONTEND_MAIN_LOCK = "odoo.bus.main_tab.frontend";
const BACKEND_TAB_LOCK = "odoo.bus.main_tab.backend";

export const multiTabService = {
    start() {
        const bus = new EventBus();
        const locks = browser.navigator?.locks;
        let isMain = false;
        // Terminal (public `unregister()`, e.g. bus_service on BUS:OUTDATED
        // keeping stale-code tabs out of main-tab duties): a terminated tab must
        // never re-acquire, not even after a bfcache restore.
        let terminated = false;
        // Resolves once the current acquisition attempt has settled our status
        // (main, or queued behind another tab). Recreated on each attempt so
        // `isOnMainTab()` reflects the latest attempt after a bfcache re-acquire.
        let settled = new Deferred();
        // Resolves the held-lock promise to release the lock (give up main).
        // Null when this tab does not hold the lock.
        let releaseHeld = null;
        // The main lock as this tab holds it: `lost` once another tab took it
        // over, which the lock callback still running must not undo.
        let grant = null;
        // Releases this tab's side lock: BACKEND_TAB_LOCK for a backend tab,
        // FRONTEND_MAIN_LOCK for a website tab while it is main.
        let releaseSide = null;
        // Aborts a pending (queued) acquisition; fresh per attempt.
        let abortController = null;
        // Monotonic token identifying the current acquisition attempt. Bumped by
        // every `acquire()` and by `deactivate()`, so a lock grant that lands
        // after its attempt was superseded (a bfcache re-acquire) or torn down
        // (`deactivate`/`unregister`) can be recognised and dropped. The
        // fast-path `ifAvailable` request carries no abort signal (the spec
        // forbids combining it with `ifAvailable`), so this token is the only
        // thing that can stop its callback from seizing the lock on a dead tab.
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

        /**
         * Resolves once `name` is granted; it is held until `releaseSide()`.
         */
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
                // The attempt was terminated or superseded before the browser
                // granted the lock. Returning without a pending promise releases
                // the lock synchronously so the next waiter can take over;
                // seizing it here would wedge the election (the tab never runs
                // main-tab duties yet holds the lock forever).
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
                    // Queued behind the backend tab's request, then released.
                    queueMain(myAttempt);
                    return;
                }
            }
            isMain = true;
            settled.resolve();
            bus.trigger("become_main_tab");
            // Keeping this promise pending is what holds the lock; resolving it
            // (releaseHeld) releases the lock so the next waiter can take over.
            const held = new Deferred();
            releaseHeld = () => held.resolve();
            return held;
        }

        function onMainLockError(error, myAttempt) {
            if (error?.name !== "AbortError") {
                // Refused outright (e.g. SecurityError in an opaque-origin
                // frame): no tab can arbitrate through the lock, so behave as
                // without the API rather than leave every isOnMainTab() waiting.
                console.warn("Main-tab lock refused; this tab acts as main:", error);
                // No website tab may yield to a backend tab out of the election.
                dropSide();
                becomeMainWithoutLocks();
                return;
            }
            if (!grant || !isCurrent(myAttempt)) {
                // A queued request this tab aborted itself.
                return;
            }
            // Held, and taken over by a backend tab: wait for it again.
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
                // No Web Locks API (very old browser): degrade to "this tab is
                // main" so a single-tab user still gets notifications/sounds.
                // The rare no-locks multi-tab case may duplicate them — an
                // acceptable fallback for a browser this fork does not target.
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
            // Fast path: try to grab the lock immediately so our status settles
            // without waiting. If another tab already holds it, settle "not
            // main" now and queue a blocking request for when it is released.
            //
            // The Web Locks spec forbids combining `signal` with `ifAvailable`
            // (it throws NotSupportedError), and it isn't needed here: an
            // `ifAvailable` request never waits, so there is nothing to abort,
            // and once granted the lock is held by `holdMain`'s pending
            // promise and released via `releaseHeld` — not via the signal. Only
            // the blocking request waits, so only it takes the signal.
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
            // Give up main (or stop waiting), but keep the right to re-acquire
            // on a bfcache `pageshow`. `no_longer_main_tab` fires synchronously
            // so `isOnMainTab()` reflects the change immediately.
            if (isMain) {
                isMain = false;
                bus.trigger("no_longer_main_tab");
            }
            // Invalidate the in-flight attempt: a fast-path (`ifAvailable`) grant
            // cannot be aborted via the signal, so bumping the token is what
            // stops its callback from re-seizing the lock on this torn-down tab.
            attempt++;
            // Settle the current wait before the token bump orphans it: the
            // lock callbacks armed by `acquire()` all early-return once their
            // attempt is superseded, so none of them would ever resolve it and
            // every pending `isOnMainTab()` would hang forever. The status IS
            // known here -- this tab is not main.
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
