// @ts-check
/** @odoo-module native */

import { Component, markRaw, proxy, t, useProps, xml } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { provideChildDialogContext } from "@web/core/dialog_context_hooks";
import { registry } from "@web/core/registry";
import { warnUnknownOptions } from "@web/ui/overlay/presenter";

const DIALOG_OPTIONS = new Set(["pluginManager", "onClose", "rootId", "sequence"]);

registry
    .category("dialogs")
    .addValidation((entry) => entry?.prototype instanceof Component);

class DialogWrapper extends Component {
    static template = xml`<t t-component="this.props.subComponent" t-props="this.props.subProps" />`;
    static props = {
        subComponent: t.function(),
        subProps: t.object(),
        subEnv: t.object(),
    };
    props = useProps(this.constructor.props);
    setup() {
        provideChildDialogContext({ dialogData: this.props.subEnv });
    }
}

/**
 * @typedef {{
 * onClose?(closeParams?: any): unknown;
 * pluginManager?: object;
 * rootId?: string;
 * sequence?: number;
 * }} DialogServiceInterfaceAddOptions
 */

/**
 * @typedef {{
 * add(
 * Component: (new (props: any, env: import("@web/env").OdooEnv) => import("@odoo/owl").Component),
 * props?: Record<string, any>,
 * options?: DialogServiceInterfaceAddOptions
 * ): (closeParams?: any) => Promise<void>;
 * closeAll(params?: any): Promise<void>;
 * destroy(): void;
 * }} DialogServiceInterface
 */

const log = makeLogger("web.ui.dialog");

/** @type {Set<DialogService>} */
const activeServices = new Set();
/** @type {{ top: number, left: number } | null} */
let scrollOrigin = null;

export class DialogService {
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {{ overlay: any }} services
     */
    constructor(env, { overlay }) {
        this.env = env;
        this.overlay = overlay;
        /** @type {Array<{ id: number, close: Function, isActive: boolean, scrollToOrigin?: () => void }>} */
        this.stack = [];
        this.nextId = 0;
    }

    syncBodyClass() {
        if (this.stack.length) {
            activeServices.add(this);
        } else {
            activeServices.delete(this);
        }
        document.body.classList.toggle("modal-open", activeServices.size > 0);
    }

    deactivate() {
        for (const subEnv of this.stack) {
            subEnv.isActive = false;
        }
    }

    /**
     * @param {(new (props: any, env: import("@web/env").OdooEnv) => import("@odoo/owl").Component)} dialogClass
     * @param {Record<string, any>} [props]
     * @param {DialogServiceInterfaceAddOptions} [options]
     * @returns {(closeParams?: any) => Promise<void>}
     */
    add(dialogClass, props, options = {}) {
        warnUnknownOptions("dialog", options, DIALOG_OPTIONS);
        const id = this.nextId++;
        log.lifecycle("add", () => ({
            id,
            dialog: dialogClass.name,
            options: Object.keys(options),
        }));
        const close = (/** @type {any} */ params) => {
            subEnv.isClosing = true;
            // a closing dialog no longer blocks the page: what its closing
            // does there (restoring the editor's selection, focusing a field)
            // runs before the next render unmounts it
            subEnv.releasePage?.();
            return remove(params);
        };
        const subEnv = proxy(
            /** @type {{ id: number, close: Function, isActive: boolean, isClosing: boolean, scrollToOrigin?: () => void, releasePage?: () => void }} */ ({
                id,
                close,
                isActive: true,
                isClosing: false,
            }),
        );

        subEnv.scrollToOrigin = () => {
            if (!activeServices.size && scrollOrigin) {
                browser.scrollTo(scrollOrigin);
                scrollOrigin = null;
            }
        };

        const remove = this.overlay.add(
            DialogWrapper,
            {
                subComponent: dialogClass,
                subProps: markRaw({ ...props, close }),
                subEnv,
            },
            {
                pluginManager: options.pluginManager,
                // synchronous unless onClose is not, as the presenter's: the
                // dialog then leaves in the render that closes it
                onRemove: (/** @type {any} */ closeParams) => {
                    const finish = () => {
                        const idx = this.stack.findIndex((d) => d.id === id);
                        if (idx !== -1) {
                            this.stack.splice(idx, 1);
                        }
                        subEnv.isClosing = false;
                        this.deactivate();
                        if (this.stack.length) {
                            /** @type {{ isActive: boolean }} */ (
                                this.stack.at(-1)
                            ).isActive = true;
                        }
                        this.syncBodyClass();
                    };
                    let result;
                    try {
                        result = options.onClose?.(closeParams);
                    } catch (error) {
                        finish();
                        throw error;
                    }
                    const pending = /** @type {PromiseLike<unknown> | undefined} */ (
                        result
                    );
                    if (typeof pending?.then === "function") {
                        return Promise.resolve(pending).finally(finish);
                    }
                    finish();
                },
                rootId: options.rootId,
                sequence: options.sequence,
            },
        );

        // Commit service state only after the overlay and its props were created.
        if (!activeServices.size) {
            scrollOrigin = { top: browser.scrollY, left: browser.scrollX };
        }
        this.deactivate();
        this.stack.push(subEnv);
        this.syncBodyClass();

        return close;
    }

    /**
     * @param {any} [params]
     * @returns {Promise<void>}
     */
    async closeAll(params) {
        await Promise.all(
            this.stack.toReversed().map((dialog) => dialog.close(params)),
        );
    }

    destroy() {
        const ownedDialogs = this.stack.length > 0;
        this.closeAll().catch(() => {});
        this.stack.length = 0;
        this.nextId = 0;
        this.syncBodyClass();
        if (ownedDialogs && !activeServices.size) {
            scrollOrigin = null;
        }
        log.lifecycle("destroy", () => ({
            ownedDialogs,
            activeServices: activeServices.size,
        }));
    }
}

export const dialogService = {
    dependencies: ["overlay"],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {{ overlay: any }} services
     * @returns {DialogService}
     */
    start(env, services) {
        return new DialogService(env, services);
    },
};

registry.category("services").add("dialog", dialogService);
