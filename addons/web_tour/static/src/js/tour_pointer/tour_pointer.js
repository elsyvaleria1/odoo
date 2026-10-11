/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { AppEvent } from "@web/core/events";
import { usePosition } from "@web/core/position/position_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

/**
 * @typedef {import("./tour_pointer_state").TourPointerState} TourPointerState
 * @typedef TourPointerProps
 * @property {TourPointerState} pointerState
 * @property {boolean} bounce
 */

/** @extends {Component<TourPointerProps, any>} */
export class TourPointer extends Component {
    static props = {
        pointerState: t.object({
            anchor: t.instanceOf(HTMLElement).optional(),
            content: t.string().optional(),
            isOpen: t.boolean().optional(),
            isVisible: t.boolean().optional(),
            isZone: t.boolean().optional(),
            onClick: t.or([t.function(), t.literal(null)]).optional(),
            onMouseEnter: t.or([t.function(), t.literal(null)]).optional(),
            onMouseLeave: t.or([t.function(), t.literal(null)]).optional(),
            position: t
                .or([
                    t.literal("left"),
                    t.literal("right"),
                    t.literal("top"),
                    t.literal("bottom"),
                ])
                .optional(),
            rev: t.number().optional(),
        }),
        bounce: t.boolean().optional(true),
    };

    static template = "web_tour.TourPointer";
    static width = 28;
    static height = 28;
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        const positionOptions = {
            margin: 6,
            onPositioned: (pointer, position) => {
                pointer.style.removeProperty("bottom");
                pointer.style.removeProperty("right");
                const popperRect = pointer.getBoundingClientRect();
                const { top, left, direction } = position;
                if (direction === "top") {
                    pointer.style.bottom = `${window.innerHeight - top - popperRect.height}px`;
                    pointer.style.removeProperty("top");
                } else if (direction === "left") {
                    pointer.style.right = `${window.innerWidth - left - popperRect.width}px`;
                    pointer.style.removeProperty("left");
                }
            },
        };
        Object.defineProperty(positionOptions, "position", {
            get: () => this.position,
            set: () => {},
            enumerable: true,
        });
        const rootRef = (this.rootRef = elementRef());
        const position = usePosition(
            rootRef,
            () => this.props.pointerState.anchor,
            positionOptions,
        );
        const zoneRef = (this.zoneRef = elementRef());
        /** @type {DOMREct | null} */
        let dimensions = null;
        let lastMeasuredContent = null;
        let lastOpenState = this.isOpen;
        let lastAnchor;
        let [anchorX, anchorY] = [0, 0];
        useLayoutEffect(() => {
            const { el: pointer } = rootRef;
            const { el: zone } = zoneRef;
            if (pointer) {
                const hasContentChanged = lastMeasuredContent !== this.content;
                const hasOpenStateChanged = lastOpenState !== this.isOpen;
                lastOpenState = this.isOpen;

                if (this.props.pointerState.isZone) {
                    const { anchor } = this.props.pointerState;
                    let offsetLeft = 0;
                    let offsetTop = 0;
                    if (document !== anchor.ownerDocument) {
                        const iframe = [...document.querySelectorAll("iframe")].filter(
                            (e) => e.contentDocument === anchor.ownerDocument,
                        )[0];
                        offsetLeft = iframe.getBoundingClientRect().left;
                        offsetTop = iframe.getBoundingClientRect().top;
                    }
                    const { left, top, width, height } = anchor.getBoundingClientRect();
                    zone.style.minWidth = width + "px";
                    zone.style.minHeight = height + "px";
                    zone.style.left = left + offsetLeft + "px";
                    zone.style.top = top + offsetTop + "px";
                }

                if (hasContentChanged) {
                    lastMeasuredContent = this.content;
                    pointer.style.removeProperty("width");
                    pointer.style.removeProperty("height");
                    dimensions = pointer.getBoundingClientRect();
                }

                if (hasContentChanged || hasOpenStateChanged) {
                    const [width, height] = this.isOpen
                        ? [dimensions.width, dimensions.height]
                        : [this.constructor.width, this.constructor.height];
                    if (this.isOpen) {
                        pointer.style.removeProperty("transition");
                    } else {
                        pointer.style.setProperty("transition", "none");
                    }
                    pointer.style.setProperty("width", `${width}px`);
                    pointer.style.setProperty("height", `${height}px`);
                }

                if (!this.isOpen) {
                    const { anchor } = this.props.pointerState;
                    if (anchor === lastAnchor) {
                        const { x, y, width } = anchor.getBoundingClientRect();
                        const [lastAnchorX, lastAnchorY] = [anchorX, anchorY];
                        [anchorX, anchorY] = [x, y];
                        const delta = Math.sqrt(
                            Math.pow(x - lastAnchorX, 2) + Math.pow(y - lastAnchorY, 2),
                        );
                        if (delta < 1) {
                            position.lock();
                            return;
                        }
                        const wouldOverflow =
                            window.innerWidth - x - width / 2 < dimensions?.width;
                        pointer.classList.toggle("o_expand_left", wouldOverflow);
                    }
                    lastAnchor = anchor;
                    position.unlock();
                }
            } else {
                lastMeasuredContent = null;
                lastOpenState = false;
                lastAnchor = null;
                dimensions = null;
            }
        });
        this.state = proxy({ triggerBelow: false });
        const uiService = useService("ui");
        const onActiveElementChanged = () => {
            const activeEl = uiService.activeElement;
            const pointerAnchor = this.props.pointerState.anchor;
            if (pointerAnchor) {
                this.state.triggerBelow = !activeEl.contains(pointerAnchor);
            }
        };
        useBus(uiService.bus, AppEvent.ACTIVE_ELEMENT_CHANGED, onActiveElementChanged);
    }

    get isVisible() {
        return this.props.pointerState.isVisible && !this.state.triggerBelow;
    }

    get content() {
        return this.props.pointerState.content || "";
    }

    get isOpen() {
        return this.props.pointerState.isOpen && this.content;
    }

    get position() {
        return this.props.pointerState.position || "top";
    }

    async onStopClicked() {
        await this.orm.call("res.users", "switch_tour_enabled", [false]);
        browser.location.reload();
    }
}
