// @ts-check
/** @odoo-module native */

import { Component, onWillDestroy, proxy, t, useProps, useScope } from "@odoo/owl";
import { reportUncaught } from "@web/core/errors/error_utils";
import { defineScope } from "@web/core/scope";
import { sortBy } from "@web/core/utils/collections/arrays";
import { ErrorHandler } from "@web/core/utils/components";
import { elementRef } from "@web/core/utils/element_ref";
import { useServices } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { rootIdOf } from "@web/ui/overlay/root_id";
import { serviceBackedItems } from "@web/ui/service_backed_items";

const envScope = defineScope("web/ui/overlay/overlay_container");

const OVERLAY_SYMBOL = Symbol("Overlay");

export const DEFAULT_OVERLAY_SEQUENCE = 50;

const OVERLAY_ITEMS = Symbol("OverlayItems");

/** @returns {{ contains: (target: EventTarget | null) => boolean } | undefined} */
export function useOverlayScope() {
    return /** @type {any} */ (envScope.use())[OVERLAY_SYMBOL];
}

/** @param {any[]} items */
function provideOverlayItems(items) {
    envScope.provide({ [OVERLAY_ITEMS]: items });
}

/** @returns {any[]} */
function useOverlayItems() {
    return /** @type {any} */ (envScope.use())[OVERLAY_ITEMS];
}

/**
 * @param {object | undefined} hostPluginManager
 * @param {{ contains: (target: EventTarget | null) => boolean }} scope
 */
function provideHostedOverlayScope(hostPluginManager, scope) {
    if (hostPluginManager) {
        // the item is rendered here but belongs to its caller: its scopes (and
        // the ones its children look up) are the caller's
        useScope().pluginManager = /** @type {any} */ (hostPluginManager);
    }
    envScope.provide({ [OVERLAY_SYMBOL]: scope });
}

class OverlayItem extends Component {
    static template = "web.OverlayContainer.Item";
    static props = {
        component: t.function(),
        props: t.object(),
        pluginManager: t.object().optional(),
        sequence: t.number().optional(),
        id: t.number().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    rootRef;
    /** @type {OverlayItem[]} */
    siblings;

    setup() {
        this.rootRef = elementRef();

        this.siblings = /** @type {OverlayItem[]} */ (useOverlayItems());
        this.siblings.push(this);
        onWillDestroy(() => {
            const index = this.siblings.indexOf(this);
            if (index >= 0) {
                this.siblings.splice(index, 1);
            }
        });

        provideHostedOverlayScope(this.props.pluginManager, {
            contains: (/** @type {EventTarget | null} */ target) =>
                this.contains(target),
        });
    }

    /** @returns {number} */
    get stackSequence() {
        return this.props.sequence ?? DEFAULT_OVERLAY_SEQUENCE;
    }

    /** @returns {number} */
    get stackId() {
        return this.props.id ?? 0;
    }

    /**
     * @param {OverlayItem} other
     * @returns {boolean}
     */
    isAtOrBelow(other) {
        const sequence = this.stackSequence;
        const otherSequence = other.stackSequence;
        return (
            otherSequence > sequence ||
            (otherSequence === sequence && other.stackId >= this.stackId)
        );
    }

    /**
     * @param {EventTarget} target
     * @returns {boolean}
     */
    contains(target) {
        const node = /** @type {Node} */ (target);
        return this.siblings.some(
            (oi) => this.isAtOrBelow(oi) && oi.rootRef.el?.contains(node),
        );
    }
}

export class OverlayContainer extends Component {
    static template = "web.OverlayContainer";
    static components = { ErrorHandler, OverlayItem };
    static serviceName = "overlay";
    static itemsKey = "overlays";
    static props = { overlays: t.object().optional(), rootId: t.string().optional() };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    root;
    /** @type {{ rootId: string | undefined }} */
    state;
    /** @type {Record<string | number, any>} */
    overlays;
    /** @type {Map<symbol, string | undefined>} */
    containerRoots;

    setup() {
        this.appServices = useServices();
        this.root = elementRef();
        this.state = proxy({ rootId: this.props.rootId });
        this.overlays = proxy(serviceBackedItems(this, this.props.overlays));
        this.containerRoots = proxy(this.service?.containerRoots ?? new Map());
        provideOverlayItems([]);
        if (!this.props.rootId) {
            useLayoutEffect(
                () => {
                    this.state.rootId = rootIdOf(this.root.el);
                },
                () => [this.root.el],
            );
        }
        useLayoutEffect(
            (rootId) => this.service?.registerContainer(rootId),
            () => [this.state.rootId],
        );
    }

    /** @returns {any} */
    get service() {
        return this.appServices?.[/** @type {any} */ (this.constructor).serviceName];
    }

    /** @returns {boolean} */
    get adoptsUnrooted() {
        const { rootId } = this.state;
        if (rootId === undefined) {
            return false;
        }
        const rootIds = [...this.containerRoots.values()];
        return !rootIds.includes(undefined) && rootIds.indexOf(rootId) === 0;
    }

    /** @returns {Object[]} */
    get sortedOverlays() {
        const { rootId } = this.state;
        const adoptsUnrooted = this.adoptsUnrooted;
        const mine = Object.values(
            /** @type {Record<string, any>} */ (this.overlays),
        ).filter(
            (overlay) =>
                !overlay.hasErrored &&
                (overlay.rootId === rootId ||
                    (adoptsUnrooted && overlay.rootId === undefined)),
        );
        return sortBy(mine, (overlay) => overlay.sequence);
    }

    /**
     * @param {Record<string, any>} overlay
     * @param {Error} error
     */
    handleError(overlay, error) {
        overlay.hasErrored = true;
        overlay.remove();
        reportUncaught(error);
    }
}
