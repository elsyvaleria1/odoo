// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";

import { FlowPort } from "./flow_port.js";
import { getNodeSize } from "./geometry/nodes.js";
import {
    DEFAULT_NODE_HEADER_HEIGHT,
    getNodeHeaderHeight,
    getPortOffset as computePortOffset,
} from "./geometry/ports.js";

/**
 * @typedef FlowNodeEventParams
 * @property {import("./flow_types").FlowNode} node
 * @property {Event} originalEvent
 */

/**
 * @typedef FlowNodeProps
 * @property {import("./flow_types").FlowConnection[]} connections
 * @property {number} defaultHeaderHeight
 * @property {import("./flow_types").FlowSize} defaultSize
 * @property {(node: import("./flow_types").FlowNode) => (typeof Component) | undefined} getNodeComponent
 * @property {(nodeId: import("./flow_types").FlowNodeId, portId: import("./flow_types").FlowPortId) => ("valid" | "invalid" | undefined)} getPortValidation
 * @property {boolean} hasConnectedPath
 * @property {typeof Component} [NodeComponent]
 * @property {import("./flow_types").FlowNode} node
 * @property {(params: FlowNodeEventParams) => void} onClick
 * @property {(params: {node: import("./flow_types").FlowNode}) => void} onDelete
 * @property {(params: FlowNodeEventParams) => void} onNodePointerDown
 * @property {(params: import("./flow_port").FlowPortPointerDownParams) => void} onPortPointerDown
 * @property {(params: FlowNodeEventParams) => void} onResizePointerDown
 * @property {boolean} readonly
 * @property {boolean} selected
 */

/** @extends {Component<FlowNodeProps>} */
export class FlowNode extends Component {
    static template = "web.FlowNode";
    static components = { FlowPort };
    static props = {
        connections: t.array(),
        defaultHeaderHeight: t.number().optional(DEFAULT_NODE_HEADER_HEIGHT),
        defaultSize: t.object(),
        getNodeComponent: t.function().optional(() => () => undefined),
        getPortValidation: t.function().optional(() => () => undefined),
        hasConnectedPath: t.boolean().optional(true),
        NodeComponent: t.any().optional(),
        node: t.object(),
        onClick: t.function().optional(() => () => {}),
        onDelete: t.function().optional(() => () => {}),
        onNodePointerDown: t.function().optional(() => () => {}),
        onPortPointerDown: t.function().optional(() => () => {}),
        onResizePointerDown: t.function().optional(() => () => {}),
        readonly: t.boolean().optional(false),
        selected: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    get label() {
        return (
            this.props.node.data?.label ||
            this.props.node.record?.data?.display_name ||
            this.props.node.record?.data?.name ||
            this.props.node.type
        );
    }

    get nodeComponent() {
        return this.props.getNodeComponent(this.props.node) || this.props.NodeComponent;
    }

    get nodeComponentProps() {
        return {
            node: this.props.node,
            readonly: Boolean(this.props.readonly || this.props.node.readonly),
        };
    }

    get style() {
        const size = getNodeSize(this.props.node, this.props.defaultSize);
        return `left: ${this.props.node.position.x}px; top: ${this.props.node.position.y}px; width: ${size.width}px; height: ${size.height}px;`;
    }

    get headerStyle() {
        const size = getNodeSize(this.props.node, this.props.defaultSize);
        const headerHeight = getNodeHeaderHeight(
            this.props.node,
            size,
            this.props.defaultHeaderHeight,
        );
        return `height: ${headerHeight}px;`;
    }

    get deleteLabel() {
        return _t("Delete node");
    }

    /**
     * @param {import("./flow_types").FlowPortId} portId
     * @returns {boolean}
     */
    isPortConnected(portId) {
        return this.props.connections.some(
            (connection) =>
                (connection.sourceNodeId === this.props.node.id &&
                    connection.sourcePortId === portId) ||
                (connection.targetNodeId === this.props.node.id &&
                    connection.targetPortId === portId),
        );
    }

    /**
     * @param {import("./flow_types").FlowPortId} portId
     * @returns {number}
     */
    getPortOffset(portId) {
        const size = getNodeSize(this.props.node, this.props.defaultSize);
        const offset = computePortOffset(
            this.props.node,
            portId,
            this.props.defaultSize,
            this.props.defaultHeaderHeight,
        );
        return (offset ?? 0) / size.height;
    }

    /**
     * @param {import("./flow_types").FlowPortId} portId
     * @returns {"valid" | "invalid" | undefined}
     */
    getPortValidation(portId) {
        return this.props.getPortValidation(this.props.node.id, portId);
    }

    /** @param {MouseEvent | KeyboardEvent} ev */
    onClick(ev) {
        this.props.onClick({
            node: this.props.node,
            originalEvent: ev,
        });
    }

    /** @param {MouseEvent} ev */
    onDeleteClick(ev) {
        ev.stopPropagation();
        this.props.onDelete({ node: this.props.node });
    }

    /** @param {PointerEvent} ev */
    onDeletePointerDown(ev) {
        ev.stopPropagation();
    }

    /** @param {PointerEvent} ev */
    onPointerDown(ev) {
        this.props.onNodePointerDown({
            node: this.props.node,
            originalEvent: ev,
        });
    }

    /** @param {MouseEvent} ev */
    onResizeClick(ev) {
        ev.stopPropagation();
    }

    /** @param {PointerEvent} ev */
    onResizePointerDown(ev) {
        ev.stopPropagation();
        this.props.onResizePointerDown({
            node: this.props.node,
            originalEvent: ev,
        });
    }

    /** @param {KeyboardEvent} ev */
    onKeyDown(ev) {
        if (ev.target !== ev.currentTarget || !["Enter", " "].includes(ev.key)) {
            return;
        }
        ev.preventDefault();
        this.onClick(ev);
    }
}
