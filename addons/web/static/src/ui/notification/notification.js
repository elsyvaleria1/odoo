// @ts-check
/** @odoo-module native */

import { Component, onMounted, onWillUnmount, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { elementRef } from "@web/core/utils/element_ref";

const AUTOCLOSE_DELAY = 4000;

const log = makeLogger("web.ui.notification");

export class Notification extends Component {
    static template = "web.NotificationWowl";
    static props = {
        message: t.customValidator(
            t.any(),
            (/** @type {unknown} */ m) =>
                typeof m === "string" ||
                (typeof m === "object" && typeof m.toString === "function"),
        ),
        type: t
            .customValidator(t.string(), (/** @type {any} */ t) =>
                ["warning", "danger", "success", "info"].includes(t),
            )
            .optional("warning"),
        title: t.or([t.string(), t.boolean(), t.any()]).optional(),
        className: t.string().optional(""),
        buttons: t
            .array(
                t.object({
                    name: t.string(),
                    icon: t.string().optional(),
                    primary: t.boolean().optional(),
                    onClick: t.function(),
                }),
            )
            .optional([]),
        sticky: t.boolean().optional(),
        autocloseDelay: t.number().optional(AUTOCLOSE_DELAY),
        close: t.function(),
    };
    props = useProps(this.constructor.props);
    /** @type {number | null} */
    closeTimeout = null;
    /** @type {number} */
    timerStart = 0;
    remainingDelay = 0;
    /** @type {Set<"hover" | "focus">} */
    holds = new Set();

    setup() {
        this.rootRef = elementRef();
        this.autocloseProgress = elementRef();
        this.remainingDelay = this.props.autocloseDelay;
        onMounted(() => this.startNotificationTimer());
        onWillUnmount(() => this.stopNotificationTimer());
    }

    /** @returns {boolean} */
    get isAssertive() {
        return ["danger", "warning"].includes(this.props.type);
    }

    /**
     * @param {Node | null} [relatedTarget]
     * @returns {boolean}
     */
    isInternalTransition(relatedTarget) {
        return (
            relatedTarget instanceof Node &&
            Boolean(this.rootRef.el?.contains(relatedTarget))
        );
    }

    /**
     * @param {"hover" | "focus"} reason
     * @param {boolean} held
     * @param {FocusEvent | MouseEvent} [ev]
     */
    setHold(reason, held, ev) {
        if (this.isInternalTransition(/** @type {Node | null} */ (ev?.relatedTarget))) {
            return;
        }
        const wasHeld = this.holds.size > 0;
        if (held) {
            this.holds.add(reason);
        } else {
            this.holds.delete(reason);
        }
        const isHeld = this.holds.size > 0;
        if (isHeld === wasHeld) {
            return;
        }
        let outcome = "pause";
        if (held) {
            this.pauseNotificationTimer();
        } else if (this.remainingDelay > 0) {
            outcome = "resume";
            this.startNotificationTimer();
        } else if (!this.props.sticky) {
            outcome = "close";
            this.props.close();
        } else {
            outcome = "keep";
        }
        log.logic("hold", () => ({
            reason,
            held,
            outcome,
            remainingDelay: Math.round(this.remainingDelay),
            sticky: Boolean(this.props.sticky),
        }));
    }

    pauseNotificationTimer() {
        if (this.props.sticky || !this.closeTimeout) {
            return;
        }
        const elapsed = browser.performance.now() - this.timerStart;
        this.remainingDelay = Math.max(0, this.remainingDelay - elapsed);
        browser.clearTimeout(this.closeTimeout);
        this.closeTimeout = null;
        if (this.autocloseProgress.el) {
            this.autocloseProgress.el.style.animationPlayState = "paused";
        }
    }

    startNotificationTimer() {
        if (this.props.sticky) {
            return;
        }
        if (this.closeTimeout) {
            browser.clearTimeout(this.closeTimeout);
        }
        this.timerStart = browser.performance.now();
        this.closeTimeout = browser.setTimeout(() => {
            this.remainingDelay = 0;
            log.logic("autoclose", () => ({ type: this.props.type }));
            this.props.close();
        }, this.remainingDelay);
        const progressEl = this.autocloseProgress.el;
        if (progressEl) {
            if (progressEl.style.animationPlayState === "paused") {
                progressEl.style.animationPlayState = "running";
            } else {
                progressEl.style.animation = "none";
                void progressEl.offsetWidth;
                progressEl.style.animation = `o-notification-progress ${this.remainingDelay}ms linear forwards`;
                progressEl.style.animationPlayState = "running";
            }
        }
    }

    stopNotificationTimer() {
        if (this.closeTimeout) {
            browser.clearTimeout(this.closeTimeout);
            this.closeTimeout = null;
        }
    }
}
