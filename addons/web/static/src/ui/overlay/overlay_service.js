// @ts-check
/** @odoo-module native */

import { markRaw, proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { mainComponentEntry } from "@web/ui/main_components_container";
import {
    DEFAULT_OVERLAY_SEQUENCE,
    OverlayContainer,
} from "@web/ui/overlay/overlay_container";

const mainComponents = registry.category("main_components");
const services = registry.category("services");

/**
 * @typedef {{
 * pluginManager?: object;
 * onRemove?: (params?: any) => void;
 * sequence?: number;
 * rootId?: string;
 * }} OverlayServiceAddOptions
 */

const log = makeLogger("web.ui.overlay");

class OverlayService {
    constructor() {
        this.nextId = 0;
        this.overlays = proxy(/** @type {Record<number, any>} */ ({}));
        /** @type {Map<number, Promise<void>>} */
        this.removing = new Map();
        /** @type {Map<symbol, string | undefined>} */
        this.containerRoots = proxy(new Map());

        mainComponents.add("OverlayContainer", mainComponentEntry(OverlayContainer));
    }

    /**
     * @param {string | undefined} rootId
     * @returns {() => void}
     */
    registerContainer(rootId) {
        const registration = Symbol();
        this.containerRoots.set(registration, rootId);
        log.lifecycle("register container", () => ({
            rootId,
            registrations: this.containerRoots.size,
        }));
        return () => {
            if (!this.containerRoots.delete(registration)) {
                return;
            }
            log.lifecycle("unregister container", () => ({
                rootId,
                registrations: this.containerRoots.size,
            }));
        };
    }

    /**
     * @param {number} id
     * @param {(params?: any) => any} [onRemove]
     * @param {any} [removeParams]
     * @returns {Promise<void>}
     */
    _remove(id, onRemove = () => {}, removeParams) {
        log.lifecycle("remove", () => ({
            id,
            component: this.overlays[id]?.component?.name,
            known: id in this.overlays,
            inFlight: this.removing.has(id),
        }));
        if (!(id in this.overlays)) {
            return Promise.resolve();
        }
        const pending = this.removing.get(id);
        if (pending) {
            if (odoo.debug && removeParams !== undefined) {
                console.warn(
                    `[overlay] closing overlay ${id} again while its removal ` +
                        `is in flight: the provided removeParams are ignored.`,
                );
            }
            return pending;
        }
        let result;
        try {
            result = onRemove(removeParams);
        } catch (error) {
            delete this.overlays[id];
            return Promise.reject(error);
        }
        if (typeof result?.then !== "function") {
            // settled now: the overlay leaves in the render that removes it,
            // not one after, so a sibling mounting meanwhile is not restarted
            delete this.overlays[id];
            return Promise.resolve();
        }
        const { promise, resolve, reject } = /** @type {PromiseWithResolvers<void>} */ (
            Promise.withResolvers()
        );
        this.removing.set(id, promise);
        (async () => {
            try {
                await result;
                resolve();
            } catch (error) {
                reject(error);
            } finally {
                this.removing.delete(id);
                delete this.overlays[id];
            }
        })();
        return promise;
    }

    /**
     * @param {(new (props: any, env: import("@web/env").OdooEnv) => import("@odoo/owl").Component)} component
     * @param {object} props
     * @param {OverlayServiceAddOptions} [options]
     * @returns {(removeParams?: any) => Promise<void>}
     */
    add(component, props, options = {}) {
        const id = ++this.nextId;
        const removeCurrentOverlay = (/** @type {any} */ removeParams = undefined) =>
            this._remove(id, options.onRemove, removeParams);
        this.overlays[id] = {
            id,
            component,
            pluginManager: options.pluginManager && markRaw(options.pluginManager),
            props: props && markRaw(props),
            remove: removeCurrentOverlay,
            sequence: options.sequence ?? DEFAULT_OVERLAY_SEQUENCE,
            rootId: options.rootId,
        };
        log.lifecycle("add", () => ({
            id,
            component: component.name,
            sequence: this.overlays[id].sequence,
            rootId: options.rootId,
            open: Object.keys(this.overlays).length,
        }));
        return removeCurrentOverlay;
    }

    destroy() {
        for (const id of Object.keys(this.overlays)) {
            this.overlays[Number(id)].remove().catch(() => {});
        }
    }
}

export const overlayService = {
    /** @returns {OverlayService} */
    start() {
        return new OverlayService();
    },
};

services.add("overlay", overlayService);
