// @ts-check
/** @odoo-module native */

import { Component, markRaw, onWillDestroy, proxy, useProps, xml } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { AppEvent } from "@web/core/events";
import { elementRef } from "@web/core/utils/element_ref";
import { useEventBus } from "@web/core/utils/hooks";

const log = makeLogger("web.action.container");

const POINTER_TARGET_MAX_DESCENDANTS = 16;

/** @returns {Element | undefined} */
function elementUnderPointer() {
    return [...document.querySelectorAll(":hover")].at(-1);
}

/**
 * @param {Element | undefined} target
 * @returns {() => void}
 */
export function showProgressCursor(target) {
    if (
        !(target instanceof HTMLElement) ||
        target.getElementsByTagName("*").length > POINTER_TARGET_MAX_DESCENDANTS
    ) {
        return () => {};
    }
    const { style } = target;
    const cursor = style.getPropertyValue("cursor");
    const priority = style.getPropertyPriority("cursor");
    style.setProperty("cursor", "progress", "important");
    return () => style.setProperty("cursor", cursor, priority);
}

export class ActionContainer extends Component {
    static props = {};
    static template = xml`
        <t t-name="web.ActionContainer">
          <div class="o_action_manager" t-ref="this.rootRef">
            <t t-set="info" t-value="this.state.info"/>
            <t t-if="info.Component" t-component="info.Component" className="'o_action'" t-props="info.componentProps" t-key="info.id"/>
          </div>
        </t>`;
    props = useProps(this.constructor.props);

    setup() {
        this.bus = useEventBus();
        this.state = proxy({ info: markRaw({}) });
        this.rootRef = elementRef();
        this.busyHolds = 0;
        /** @type {() => void} */
        this.givePointerBack = () => {};
        /** @param {Event} event */
        this.onPointerOver = ({ target }) =>
            this.pointAt(target instanceof Element ? target : undefined);
        /** @type {(() => void) | null} */
        this.releaseAction = null;
        /** @param {CustomEvent} event */
        useLifecycleLog(log);
        this.onActionManagerUpdate = ({ detail: info }) => {
            log.pipeline("update", () => ({
                id: info.id,
                component: info.Component?.name,
                jsId: info.componentProps?.jsId,
            }));
            info.settled?.then(this.holdBusy());
            this.state.info = markRaw(info);
        };
        this.onActionStarted = () => {
            this.releaseAction?.();
            this.releaseAction = this.holdBusy();
        };
        this.onActionSettled = () => {
            this.releaseAction?.();
            this.releaseAction = null;
        };
        const listeners = /** @type {const} */ ([
            [AppEvent.ACTION_MANAGER_UPDATE, this.onActionManagerUpdate],
            [AppEvent.ACTION_MANAGER_STARTED, this.onActionStarted],
            [AppEvent.ACTION_MANAGER_SETTLED, this.onActionSettled],
        ]);
        for (const [eventName, listener] of listeners) {
            this.bus.addEventListener(eventName, listener);
        }
        onWillDestroy(() => {
            for (const [eventName, listener] of listeners) {
                this.bus.removeEventListener(eventName, listener);
            }
            this.stopPointing();
        });
    }

    /** @param {Element | undefined} [target] */
    pointAt(target) {
        this.givePointerBack();
        this.givePointerBack = showProgressCursor(target);
    }

    stopPointing() {
        browser.removeEventListener("pointerover", this.onPointerOver, true);
        this.givePointerBack();
        this.givePointerBack = () => {};
    }

    /** @returns {() => void} */
    holdBusy() {
        if (this.busyHolds++ === 0) {
            this.rootRef.el?.setAttribute("aria-busy", "true");
            this.pointAt(elementUnderPointer());
            browser.addEventListener("pointerover", this.onPointerOver, true);
        }
        let isHeld = true;
        return () => {
            if (isHeld && --this.busyHolds === 0) {
                this.rootRef.el?.removeAttribute("aria-busy");
                this.stopPointing();
            }
            isHeld = false;
        };
    }
}
