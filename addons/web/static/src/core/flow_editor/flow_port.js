// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

/**
 * @typedef FlowPortPointerDownParams
 * @property {import("./flow_types").FlowNodeId} nodeId
 * @property {import("./flow_types").FlowPort} port
 * @property {PointerEvent} originalEvent
 */

/**
 * @typedef FlowPortProps
 * @property {boolean} connected
 * @property {import("./flow_types").FlowNodeId} nodeId
 * @property {number} offset
 * @property {(params: FlowPortPointerDownParams) => void} onPointerDown
 * @property {import("./flow_types").FlowPort} port
 * @property {"valid" | "invalid"} [validation]
 */

/** @extends {Component<FlowPortProps>} */
export class FlowPort extends Component {
    static template = "web.FlowPort";
    static props = {
        connected: t.boolean().optional(false),
        nodeId: t.any(),
        offset: t.number(),
        onPointerDown: t.function().optional(() => () => {}),
        port: t.object(),
        validation: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    get style() {
        return `top: ${this.props.offset * 100}%;`;
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        ev.stopPropagation();
    }

    /** @param {PointerEvent} ev */
    onPointerDown(ev) {
        ev.stopPropagation();
        this.props.onPointerDown({
            nodeId: this.props.nodeId,
            port: this.props.port,
            originalEvent: ev,
        });
    }
}
