/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { getStrokeAndHoveredStrokeColor } from "@web/core/colors/colors";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export { getStrokeAndHoveredStrokeColor };

/**
 * @typedef {"error" | "warning"} ConnectorAlert
 * @typedef {`__connector__${number | "new"}`} ConnectorId
 * @typedef {import("./gantt_renderer_core").Point} Point
 *
 * @typedef ConnectorProps
 * @property {ConnectorId} id
 * @property {ConnectorAlert | null} alert
 * @property {boolean} highlighted
 * @property {boolean} displayButtons
 * @property {Point | () => Point | null} sourcePoint
 * @property {Point | () => Point | null} targetPoint
 *
 * @typedef {Object} PathInfo
 * @property {Point} sourceControlPoint
 * @property {Point} targetControlPoint
 * @property {Point} removeButtonPosition
 *
 * @typedef Point
 * @property {number} [left]
 * @property {number} [top]
 */

export const COLORS = {
    default: getStrokeAndHoveredStrokeColor(143, 143, 143),
    error: getStrokeAndHoveredStrokeColor(211, 65, 59),
    warning: getStrokeAndHoveredStrokeColor(236, 151, 31),
    outline: getStrokeAndHoveredStrokeColor(255, 255, 255),
};

/** @extends {Component<{ reactive: ConnectorProps }, any>} */
export class GanttConnector extends Component {
    static props = {
        reactive: t.object({
            id: t.string(),
            alert: t
                .or([t.literal("error"), t.literal("warning"), t.literal(null)])
                .optional(),
            highlighted: t.boolean().optional(),
            displayButtons: t.boolean().optional(),
            sourcePoint: t.or([
                t.literal(null),
                t.function(),
                t.object({ left: t.number(), top: t.number() }),
            ]),
            targetPoint: t.or([
                t.literal(null),
                t.function(),
                t.object({ left: t.number(), top: t.number() }),
            ]),
            dashed: t.boolean().optional(),
        }),
        onRemoveButtonClick: t.function().optional(),
        onConnectorHover: t.function(),
    };
    static template = "web_gantt.GanttConnector";
    props = useProps(this.constructor.props);

    rootRef = elementRef();

    get style() {
        const key = this.highlighted ? "highlightedColor" : "color";
        const strokeColor =
            this.props.onConnectorHover() && this.highlighted
                ? "rgba(52, 152, 219,1)"
                : COLORS[this.alert || "default"][key];
        return {
            hoverEaseWidth: 10,
            slackness: 0.9,
            stroke: { color: strokeColor, width: 2 },
            outlineStroke: { color: COLORS.outline[key], width: 1 },
        };
    }

    get alert() {
        return this.props.reactive.alert;
    }

    get displayButtons() {
        return this.props.reactive.displayButtons;
    }

    get highlighted() {
        return this.props.reactive.highlighted;
    }

    get id() {
        return this.props.reactive.id;
    }

    get isNew() {
        return this.id.endsWith("new");
    }

    get sourcePoint() {
        return this.props.reactive.sourcePoint;
    }

    get targetPoint() {
        return this.props.reactive.targetPoint;
    }

    get isDashed() {
        return this.props.reactive.dashed;
    }

    setup() {
        useLayoutEffect(
            (el, sourceLeft, sourceTop, targetLeft, targetTop) => {
                if (!el) {
                    return;
                }
                const { sourceControlPoint, targetControlPoint, removeButtonPosition } =
                    this.getPathInfo(
                        { left: sourceLeft, top: sourceTop },
                        { left: targetLeft, top: targetTop },
                        this.style.slackness,
                    );

                const drawingCommands = [
                    `M`,
                    `${sourceLeft},${sourceTop}`,
                    `C`,
                    `${sourceControlPoint.left},${sourceControlPoint.top}`,
                    `${targetControlPoint.left},${targetControlPoint.top}`,
                    `${targetLeft},${targetTop}`,
                ].join(" ");

                const paths = el.querySelectorAll(
                    ".o_connector_stroke, .o_connector_stroke_hover_ease",
                );
                for (const path of paths) {
                    path.setAttribute("d", drawingCommands);
                }

                const svgButtons = el.querySelector(".o_connector_stroke_buttons");
                if (svgButtons) {
                    svgButtons.setAttribute("x", removeButtonPosition.left - 24);
                    svgButtons.setAttribute("y", removeButtonPosition.top - 8);
                }
            },
            () => this.getEffectDependencies(),
        );
    }

    getEffectDependencies() {
        let sourcePoint = this.sourcePoint || { left: 0, top: 0 };
        if (typeof sourcePoint === "function") {
            sourcePoint = sourcePoint();
        }
        let targetPoint = this.targetPoint || { left: 0, top: 0 };
        if (typeof targetPoint === "function") {
            targetPoint = targetPoint();
        }
        const { x, y } = this.rootRef.el?.getBoundingClientRect() || { x: 0, y: 0 };

        return [
            this.rootRef.el,
            sourcePoint.left - x,
            sourcePoint.top - y,
            targetPoint.left - x,
            targetPoint.top - y,
            this.displayButtons,
        ];
    }

    /**
     * @param {Point} startingPoint
     * @param {Point} endingPoint
     * @param {number} lambda
     * @returns {Point}
     */
    getLinearInterpolation(startingPoint, endingPoint, lambda = 0.5) {
        return {
            left: lambda * startingPoint.left + (1 - lambda) * endingPoint.left,
            top: lambda * startingPoint.top + (1 - lambda) * endingPoint.top,
        };
    }

    /**
     * @param {Point} sourcePoint
     * @param {Point} targetPoint
     * @param {number} slackness [0, 1]
     * @returns {PathInfo}
     */
    getPathInfo(sourcePoint, targetPoint, slackness) {
        const xDelta = targetPoint.left - sourcePoint.left;
        const yDelta = targetPoint.top - sourcePoint.top;
        const directionFactor = Math.sign(xDelta);

        const xInc = 100 + (Math.abs(xDelta) * slackness) / 10;
        const yInc =
            Math.abs(yDelta) < 16 && directionFactor === -1
                ? 15 - 0.001 * xDelta * slackness
                : 0;

        const b = {
            left: sourcePoint.left + xInc,
            top: sourcePoint.top + yInc,
        };

        const c = {
            left:
                targetPoint.left +
                (this.isNew && directionFactor === -1 ? xInc : -xInc),
            top: targetPoint.top + yInc,
        };

        const e = this.getLinearInterpolation(sourcePoint, b);
        const f = this.getLinearInterpolation(b, c);
        const g = this.getLinearInterpolation(c, targetPoint);
        const h = this.getLinearInterpolation(e, f);
        const i = this.getLinearInterpolation(f, g);
        const j = this.getLinearInterpolation(h, i);

        return {
            sourceControlPoint: b,
            targetControlPoint: c,
            removeButtonPosition: j,
        };
    }

    onRemoveButtonClick() {
        if (this.props.onRemoveButtonClick) {
            this.props.onRemoveButtonClick(this.props.reactive.id);
        }
    }
}
