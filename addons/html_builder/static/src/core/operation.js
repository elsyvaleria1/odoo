/** @odoo-module native */
import { Mutex } from "@web/core/utils/concurrency";

/**
 * @typedef OperationParams
 * @property {Function} load
 * @property {Boolean} cancellable
 * @property {Function} cancelPrevious
 * @property {Number} [cancelTime=50]
 * @property {Boolean} [withLoadingEffect=true]
 * @property {Number} [loadingEffectDelay=500]
 * @property {Boolean} [shouldInterceptClick=false]
 * @property {Boolean} [canTimeout=true]
 * @property {Number} [timeout=10000]
 */

export class OperationMutex extends Mutex {
    constructor() {
        super();
        this._skipUntilEmpty = false;
    }

    clearQueue() {
        this._skipUntilEmpty = this._queueSize > 0;
        if (this._skipUntilEmpty) {
            this.getUnlockedDef().then(() => {
                this._skipUntilEmpty = false;
            });
        }
    }

    async exec(action) {
        return super.exec(() => {
            if (this._skipUntilEmpty) {
                return;
            }
            return action();
        });
    }
}

export class Operation {
    constructor(editableDocument = document) {
        this.mutex = new OperationMutex();
        this.editableDocument = editableDocument;
    }

    /**
     * @param {Function} fn
     * @param {OperationParams} params
     * @returns {Promise<void>}
     */
    next(
        fn,
        {
            load = () => Promise.resolve(),
            cancellable,
            cancelPrevious,
            cancelTime = 50,
            withLoadingEffect = true,
            loadingEffectDelay = 500,
            shouldInterceptClick = false,
            canTimeout = true,
            timeout = 10000,
        } = {},
    ) {
        this.cancelPrevious?.();
        let isCancel = false;
        let cancelResolve;
        this.cancelPrevious =
            cancellable &&
            (() => {
                this.cancelPrevious = null;
                isCancel = true;
                cancelResolve?.();
                this.mutex.exec(async () => {
                    await cancelPrevious?.();
                });
            });

        const cancelTimePromise = new Promise((resolve) =>
            setTimeout(resolve, cancelTime),
        );
        const cancelLoadPromise = new Promise((resolve) => {
            cancelResolve = resolve;
        });

        let hasTimedOut = false;
        return this.mutex.exec(async () => {
            if (isCancel) {
                return;
            }
            let cancelTimeoutPromise;
            if (canTimeout) {
                cancelTimeoutPromise = new Promise((resolve) => {
                    setTimeout(() => {
                        hasTimedOut = true;
                        resolve();
                    }, timeout);
                });
            }

            const removeLoadingElement = this.addLoadingElement(
                withLoadingEffect,
                loadingEffectDelay,
                shouldInterceptClick,
            );
            const applyOperation = async () => {
                const loadResult = await load();

                if (isCancel) {
                    return;
                }
                this.previousLoadResolve = null;

                if (!this.editableDocument.defaultView) {
                    return;
                }

                await fn?.(loadResult);
            };

            try {
                const promises = [
                    Promise.all([cancelLoadPromise, cancelTimePromise]),
                    applyOperation(),
                ];
                if (cancelTimeoutPromise) {
                    promises.push(cancelTimeoutPromise);
                }
                await Promise.race(promises);
            } finally {
                if (hasTimedOut) {
                    this.mutex.clearQueue();
                }
                removeLoadingElement();
            }
            return { hasFailed: hasTimedOut };
        });
    }

    /**
     * @param {Boolean} withLoadingEffect
     * @param {Number} loadingEffectDelay
     * @param {Boolean} shouldInterceptClick
     * @returns {Function}
     */
    addLoadingElement(withLoadingEffect, loadingEffectDelay, shouldInterceptClick) {
        const loadingScreenEl = document.createElement("div");
        loadingScreenEl.classList.add(
            ...[
                "o_loading_screen",
                "d-flex",
                "justify-content-center",
                "align-items-center",
            ],
        );
        const spinnerEl = document.createElement("img");
        spinnerEl.setAttribute("src", "/web/static/img/spin.svg");
        loadingScreenEl.appendChild(spinnerEl);

        let removeClickListener = () => {};
        if (shouldInterceptClick) {
            const onClick = (ev) => {
                const trueTargetEls = this.editableDocument.elementsFromPoint(
                    ev.clientX,
                    ev.clientY,
                );
                this.next(() => {
                    for (const trueTargetEl of trueTargetEls) {
                        if (trueTargetEl.isConnected) {
                            trueTargetEl.click();
                            break;
                        }
                    }
                });
            };
            this.editableDocument.addEventListener("click", onClick);
            removeClickListener = () =>
                this.editableDocument.removeEventListener("click", onClick);
        }

        this.editableDocument.body.appendChild(loadingScreenEl);

        let loadingTimeout;
        if (withLoadingEffect) {
            loadingTimeout = setTimeout(
                () => loadingScreenEl.classList.add("o_we_ui_loading"),
                loadingEffectDelay,
            );
        }

        return () => {
            if (loadingTimeout) {
                clearTimeout(loadingTimeout);
            }
            removeClickListener();
            loadingScreenEl.remove();
        };
    }
}
