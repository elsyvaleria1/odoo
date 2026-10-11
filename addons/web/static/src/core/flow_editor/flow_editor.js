// @ts-check
/** @odoo-module native */

import {
    Component,
    onMounted,
    onWillDestroy,
    onWillUpdateProps,
    proxy,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";

import {
    getConnectionValidity,
    normalizeConnectionValidation,
} from "./connection_validator.js";
import { FlowConnection } from "./flow_connection.js";
import { FlowEditorStore } from "./flow_editor_store.js";
import { FlowNode } from "./flow_node.js";
import { getConnectionGeometry } from "./geometry/connections.js";
import { clampScale, screenToWorld } from "./geometry/coordinates.js";
import {
    expandRect,
    getNodeRect,
    getNodeSize,
    getObstacleRects,
} from "./geometry/nodes.js";
import { DEFAULT_NODE_HEADER_HEIGHT, getPortAnchor } from "./geometry/ports.js";
import { getOrthogonalPath } from "./geometry/router.js";

const DEFAULT_NODE_SIZE = { width: 220, height: 120 };
const DEFAULT_MIN_NODE_SIZE = { width: 120, height: 80 };
const DEFAULT_MAX_NODE_SIZE = { width: 640, height: 480 };
const DEFAULT_GRID_SIZE = 20;
const OBSTACLE_PADDING = 20;
const DRAG_THRESHOLD = 3;

const NULL_VALUE_PROP = t.literal(null);

const log = makeLogger("web.flow_editor");

/** @typedef {PointerEvent | { pointerId: number | null, originalEvent: Event | null }} FlowCancelEvent */

/**
 * @typedef FlowEditorProps
 * @property {boolean} allowSelfConnections
 * @property {string} ariaLabel
 * @property {(connection: import("./flow_types").FlowConnection) => (boolean | string | import("./connection_validator").FlowConnectionValidation | undefined)} canConnect
 * @property {import("./flow_types").FlowConnection[]} connections
 * @property {number} defaultNodeHeaderHeight
 * @property {import("./flow_types").FlowSize} defaultNodeSize
 * @property {boolean} flagUnreachableNodes
 * @property {(connection: import("./flow_types").FlowConnection) => string | undefined} getConnectionClass
 * @property {(connection: import("./flow_types").FlowConnection) => string | undefined} getConnectionLabel
 * @property {(node: import("./flow_types").FlowNode) => (typeof Component) | undefined} getNodeComponent
 * @property {number} gridSize
 * @property {import("./flow_types").FlowSize} maxNodeSize
 * @property {import("./flow_types").FlowSize} minNodeSize
 * @property {typeof Component} [NodeComponent]
 * @property {import("./flow_types").FlowNode[]} nodes
 * @property {(connection: import("./flow_types").FlowConnection) => (import("./flow_types").FlowConnection | false | void | Promise<import("./flow_types").FlowConnection | false | void>)} onConnect
 * @property {(params: { connection: import("./flow_types").FlowConnection, validation: import("./connection_validator").FlowConnectionValidation }) => void} onConnectionRejected
 * @property {(params: { connection: import("./flow_types").FlowConnection }) => (boolean | void | Promise<boolean | void>)} onDisconnect
 * @property {(params: { phase: string, node: import("./flow_types").FlowNode | undefined, position: import("./flow_types").FlowPosition, originalEvent: Event | null }) => void} onDrag
 * @property {(params: { node: import("./flow_types").FlowNode }) => (boolean | void | Promise<boolean | void>)} onNodeDelete owns the node's connections: they leave with it, without an onDisconnect each
 * @property {(params: import("./flow_node").FlowNodeEventParams) => void} onNodeClick
 * @property {(params: { phase: string }) => void} onPan
 * @property {(params: { phase: string, node: import("./flow_types").FlowNode | undefined, size: import("./flow_types").FlowSize, originalEvent: Event | null }) => void} onResize
 * @property {(selection: import("./flow_types").FlowSelection) => void} onSelectionChange
 * @property {(viewport: import("./flow_types").FlowViewport) => void} onViewportChange
 * @property {boolean} readonly
 * @property {boolean} showControls
 * @property {import("./flow_types").FlowViewport | null} viewport
 */

/** @extends {Component<FlowEditorProps>} */
export class FlowEditor extends Component {
    static template = "web.FlowEditor";
    static components = { FlowConnection, FlowNode };
    static props = {
        allowSelfConnections: t.boolean().optional(false),
        ariaLabel: t.string().optional(),
        canConnect: t.function().optional(() => () => true),
        connections: t.array(),
        defaultNodeHeaderHeight: t.number().optional(DEFAULT_NODE_HEADER_HEIGHT),
        defaultNodeSize: t.object().optional(DEFAULT_NODE_SIZE),
        flagUnreachableNodes: t.boolean().optional(true),
        getConnectionClass: t.function().optional(() => () => ""),
        getConnectionLabel: t.function().optional(() => () => ""),
        getNodeComponent: t.function().optional(() => () => undefined),
        gridSize: t.number().optional(DEFAULT_GRID_SIZE),
        maxNodeSize: t.object().optional(DEFAULT_MAX_NODE_SIZE),
        minNodeSize: t.object().optional(DEFAULT_MIN_NODE_SIZE),
        NodeComponent: t.any().optional(),
        nodes: t.array(),
        onConnect: t
            .function()
            .optional(
                () =>
                    (/** @type {import("./flow_types").FlowConnection} */ connection) =>
                        connection,
            ),
        onConnectionRejected: t.function().optional(() => () => {}),
        onDisconnect: t.function().optional(() => () => true),
        onDrag: t.function().optional(() => () => {}),
        onNodeDelete: t.function().optional(() => () => true),
        onNodeClick: t.function().optional(() => () => {}),
        onPan: t.function().optional(() => () => {}),
        onResize: t.function().optional(() => () => {}),
        onSelectionChange: t.function().optional(() => () => {}),
        onViewportChange: t.function().optional(() => () => {}),
        readonly: t.boolean().optional(false),
        showControls: t.boolean().optional(true),
        viewport: t.or([t.object(), NULL_VALUE_PROP]).optional(null),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    canvasRef;
    /** @type {FlowEditorStore} */
    store;
    /** @type {number | null} */
    activePointerId = null;
    /** @type {{ x: number, y: number }} */
    pointerStart = { x: 0, y: 0 };
    /** @type {{ x: number, y: number }} */
    dragOffset = { x: 0, y: 0 };
    /** @type {import("./flow_types").FlowViewport} */
    panOrigin = { x: 0, y: 0, scale: 1 };
    didDrag = false;
    snapNodeDrag = false;
    suppressNodeClick = false;
    /** @type {number | null} */
    viewportAnimationFrame = null;
    framed = false;
    /** @type {ResizeObserver | null} */
    canvasObserver = null;
    /** @type {Promise<boolean> | null} */
    pendingDetach = null;
    deletingSelection = false;
    /** @type {Set<import("./flow_types").FlowNodeId>} */
    deletingNodeIds = new Set();

    setup() {
        this.canvasRef = elementRef();
        this.store = proxy(
            new FlowEditorStore({
                nodes: this.props.nodes,
                connections: this.props.connections,
                viewport: this.props.viewport,
                readonly: this.props.readonly,
            }),
        );
        onWillUpdateProps((nextProps) => this.applyProps(nextProps));
        useListener(window, "pointermove", this.onPointerMove.bind(this));
        useListener(window, "pointerup", this.onPointerUp.bind(this));
        useListener(window, "pointercancel", this.onPointerCancel.bind(this));
        useListener(window, "keydown", this.onKeyDown.bind(this));
        onMounted(() => {
            if (!this.props.viewport) {
                this.fitToContent();
            }
            this.canvasObserver = new ResizeObserver(() => this.onCanvasResize());
            this.canvasObserver.observe(this.canvasEl);
        });
        onWillDestroy(() => {
            this.cancelViewportAnimation();
            this.canvasObserver?.disconnect();
        });
    }

    /** @param {FlowEditorProps} nextProps */
    applyProps(nextProps) {
        if (
            nextProps.nodes !== this.props.nodes ||
            nextProps.connections !== this.props.connections
        ) {
            const ended = this.store.setGraph(
                { nodes: nextProps.nodes, connections: nextProps.connections },
                { nodes: this.props.nodes, connections: this.props.connections },
            );
            log.logic("graph.update", () => ({
                nodes: nextProps.nodes.length,
                connections: nextProps.connections.length,
                endedInteraction: ended?.type ?? null,
            }));
            if (ended) {
                this.pendingDetach = null;
                this.notifyInteractionCancelled(ended, null);
                this.resetPointerState();
            }
        }
        if (nextProps.viewport && nextProps.viewport !== this.props.viewport) {
            this.framed = false;
            this.store.setViewport(nextProps.viewport);
        }
        const interaction = this.store.interaction;
        if (nextProps.readonly && interaction && interaction.type !== "pan") {
            this.onPointerCancel({
                pointerId: this.activePointerId,
                originalEvent: null,
            });
        }
        this.store.setReadonly(nextProps.readonly);
    }

    /** @returns {HTMLElement | null} */
    get canvasEl() {
        return this.canvasRef.el;
    }

    focusCanvas() {
        this.canvasEl?.focus({ preventScroll: true });
    }

    get ariaLabel() {
        return this.props.ariaLabel || _t("Flow editor");
    }

    get canvasStyle() {
        const { x, y, scale } = this.store.viewport;
        const gridSize = Math.max(this.props.gridSize, 1) * scale;
        return `background-size: ${gridSize}px ${gridSize}px; background-position: ${x}px ${y}px;`;
    }

    get contentStyle() {
        const { x, y, scale } = this.store.viewport;
        return `transform: translate(${x}px, ${y}px) scale(${scale});`;
    }

    get connectionGeometries() {
        const paddedRects = this.store.nodes.map((node) => ({
            id: node.id,
            rect: expandRect(
                getNodeRect(node, this.props.defaultNodeSize),
                OBSTACLE_PADDING,
            ),
        }));
        return this.store.connections
            .map((connection) => {
                const sourceNode = this.store.getNode(connection.sourceNodeId);
                const targetNode = this.store.getNode(connection.targetNodeId);
                if (!sourceNode || !targetNode) {
                    return null;
                }
                return getConnectionGeometry({
                    connection,
                    sourceNode,
                    targetNode,
                    nodes: this.store.nodes,
                    paddedRects,
                    defaultNodeSize: this.props.defaultNodeSize,
                    defaultNodeHeaderHeight: this.props.defaultNodeHeaderHeight,
                });
            })
            .filter(Boolean);
    }

    /**
     * @param {Object} candidate
     * @param {import("./flow_types").FlowNodeId} candidate.sourceNodeId
     * @param {import("./flow_types").FlowPortId} candidate.sourcePortId
     * @param {import("./flow_types").FlowNodeId} [candidate.targetNodeId]
     * @param {import("./flow_types").FlowPortId} [candidate.targetPortId]
     * @returns {import("./geometry/connections").FlowConnectionGeometry | null}
     */
    _draftSnappedGeometry({ sourceNodeId, sourcePortId, targetNodeId, targetPortId }) {
        if (targetNodeId === undefined || targetPortId === undefined) {
            return null;
        }
        const sourceNode = this.store.getNode(sourceNodeId);
        const targetNode = this.store.getNode(targetNodeId);
        if (!sourceNode || !targetNode) {
            return null;
        }
        return getConnectionGeometry({
            connection: {
                id: "flow-connection-draft",
                sourceNodeId,
                sourcePortId,
                targetNodeId,
                targetPortId,
            },
            sourceNode,
            targetNode,
            nodes: this.store.nodes,
            defaultNodeSize: this.props.defaultNodeSize,
            defaultNodeHeaderHeight: this.props.defaultNodeHeaderHeight,
        });
    }

    get draftConnectionGeometry() {
        const interaction = this.store.interaction;
        if (interaction?.type !== "connection_drag") {
            return null;
        }
        const draft = interaction.connectionDraft;
        if (draft.pendingConnectionId !== undefined) {
            return null;
        }
        return draft.reconnectSource
            ? this._reconnectDraftGeometry(draft)
            : this._forwardDraftGeometry(draft);
    }

    /**
     * @param {import("./flow_types").FlowConnectionDraft} draft
     * @returns {import("./geometry/connections").FlowConnectionGeometry | null}
     */
    _reconnectDraftGeometry(draft) {
        const snapped =
            draft.sourceCandidateNodeId !== undefined &&
            draft.sourceCandidatePortId !== undefined
                ? this._draftSnappedGeometry({
                      sourceNodeId: draft.sourceCandidateNodeId,
                      sourcePortId: draft.sourceCandidatePortId,
                      targetNodeId: draft.targetNodeId,
                      targetPortId: draft.targetPortId,
                  })
                : null;
        if (snapped) {
            return snapped;
        }
        const targetNode =
            draft.targetNodeId === undefined
                ? undefined
                : this.store.getNode(draft.targetNodeId);
        const end =
            targetNode && draft.targetPortId !== undefined
                ? getPortAnchor(
                      targetNode,
                      draft.targetPortId,
                      this.props.defaultNodeSize,
                      this.props.defaultNodeHeaderHeight,
                  )
                : null;
        if (!end) {
            return null;
        }
        return {
            id: "flow-connection-draft",
            ...getOrthogonalPath({
                start: draft.pointer,
                end,
                obstacles: this._draftObstacles(draft.targetNodeId),
                targetRect: getNodeRect(targetNode, this.props.defaultNodeSize),
                endpointPadding: OBSTACLE_PADDING,
            }),
        };
    }

    /**
     * @param {import("./flow_types").FlowConnectionDraft} draft
     * @returns {import("./geometry/connections").FlowConnectionGeometry | null}
     */
    _forwardDraftGeometry(draft) {
        const { sourceNodeId, sourcePortId, pointer } = draft;
        const snapped =
            draft.targetNodeId === undefined
                ? null
                : this._draftSnappedGeometry({
                      sourceNodeId,
                      sourcePortId,
                      targetNodeId: draft.targetNodeId,
                      targetPortId: draft.targetPortId,
                  });
        if (snapped) {
            return snapped;
        }
        const sourceNode = this.store.getNode(sourceNodeId);
        const start =
            sourceNode &&
            getPortAnchor(
                sourceNode,
                sourcePortId,
                this.props.defaultNodeSize,
                this.props.defaultNodeHeaderHeight,
            );
        if (!start) {
            return null;
        }
        return {
            id: "flow-connection-draft",
            ...getOrthogonalPath({
                start,
                end: pointer,
                obstacles: this._draftObstacles(sourceNodeId),
                sourceRect: getNodeRect(sourceNode, this.props.defaultNodeSize),
                endpointPadding: OBSTACLE_PADDING,
            }),
        };
    }

    /**
     * @param {import("./flow_types").FlowNodeId} [anchoredNodeId]
     * @returns {import("./geometry/nodes").FlowRect[]}
     */
    _draftObstacles(anchoredNodeId) {
        return getObstacleRects(this.store.nodes, {
            defaultSize: this.props.defaultNodeSize,
            padding: OBSTACLE_PADDING,
            excludedNodeIds: new Set(
                anchoredNodeId === undefined ? [] : [anchoredNodeId],
            ),
        });
    }

    /**
     * @param {import("./flow_types").FlowConnectionId} connectionId
     * @returns {string}
     */
    getConnectionClass(connectionId) {
        const connection = this.store.getConnection(connectionId);
        return (connection && this.props.getConnectionClass(connection)) || "";
    }

    /**
     * @param {import("./flow_types").FlowConnectionId} connectionId
     * @returns {string}
     */
    getConnectionLabel(connectionId) {
        const connection = this.store.getConnection(connectionId);
        return (connection && this.props.getConnectionLabel(connection)) || "";
    }

    get isInteracting() {
        return Boolean(this.store.interaction);
    }

    get emptyLabel() {
        return _t("No nodes");
    }

    get fitLabel() {
        return _t("Fit to content");
    }

    get zoomInLabel() {
        return _t("Zoom in");
    }

    get zoomOutLabel() {
        return _t("Zoom out");
    }

    get flowLocationLabel() {
        return _t("Return to the flow");
    }

    get flowBounds() {
        if (!this.store.nodes.length) {
            return null;
        }
        const rects = this.store.nodes.map((node) =>
            getNodeRect(node, this.props.defaultNodeSize),
        );
        return {
            x1: Math.min(...rects.map((rect) => rect.x1)),
            y1: Math.min(...rects.map((rect) => rect.y1)),
            x2: Math.max(...rects.map((rect) => rect.x2)),
            y2: Math.max(...rects.map((rect) => rect.y2)),
        };
    }

    get flowCenter() {
        if (!this.store.nodes.length) {
            return null;
        }
        const centers = this.store.nodes.map((node) => {
            const rect = getNodeRect(node, this.props.defaultNodeSize);
            return {
                x: (rect.x1 + rect.x2) / 2,
                y: (rect.y1 + rect.y2) / 2,
            };
        });
        return {
            x: centers.reduce((sum, center) => sum + center.x, 0) / centers.length,
            y: centers.reduce((sum, center) => sum + center.y, 0) / centers.length,
        };
    }

    get connectedNodeIds() {
        const connectedNodeIds = new Set(
            this.store.nodes.filter((node) => !node.input).map((node) => node.id),
        );
        let previousSize;
        do {
            previousSize = connectedNodeIds.size;
            for (const connection of this.store.connections) {
                if (connectedNodeIds.has(connection.sourceNodeId)) {
                    connectedNodeIds.add(connection.targetNodeId);
                }
            }
        } while (connectedNodeIds.size !== previousSize);
        return connectedNodeIds;
    }

    get flowLocationIndicator() {
        const canvasEl = this.canvasEl;
        const target = this.flowCenter;
        if (!canvasEl || !target) {
            return null;
        }
        const canvasRect = canvasEl.getBoundingClientRect();
        const { x, y, scale } = this.store.viewport;
        const view = {
            x1: -x / scale,
            y1: -y / scale,
            x2: (canvasRect.width - x) / scale,
            y2: (canvasRect.height - y) / scale,
        };
        const hasVisibleNode = this.store.nodes.some((node) => {
            const rect = getNodeRect(node, this.props.defaultNodeSize);
            return (
                rect.x2 >= view.x1 &&
                rect.x1 <= view.x2 &&
                rect.y2 >= view.y1 &&
                rect.y1 <= view.y2
            );
        });
        if (hasVisibleNode) {
            return null;
        }
        const viewCenter = {
            x: (view.x1 + view.x2) / 2,
            y: (view.y1 + view.y2) / 2,
        };
        const angle =
            (Math.atan2(target.y - viewCenter.y, target.x - viewCenter.x) * 180) /
                Math.PI +
            45;
        return {
            angle,
            x: canvasRect.width / 2,
            y: canvasRect.height / 2,
        };
    }

    /**
     * @param {{ x: number, y: number, angle: number }} indicator
     * @returns {string}
     */
    getFlowLocationIndicatorStyle(indicator) {
        return `left: ${indicator.x}px; top: ${indicator.y}px; transform: translate(-50%, -50%) rotate(${indicator.angle}deg);`;
    }

    /**
     * @param {import("./flow_types").FlowNodeId} nodeId
     * @param {import("./flow_types").FlowPortId} portId
     * @returns {"valid" | "invalid" | undefined}
     */
    getPortValidation(nodeId, portId) {
        const interaction = this.store.interaction;
        const draft =
            interaction?.type === "connection_drag"
                ? interaction.connectionDraft
                : undefined;
        if (!draft) {
            return;
        }
        if (draft.reconnectSource) {
            if (
                draft.sourceCandidateNodeId !== nodeId ||
                draft.sourceCandidatePortId !== portId
            ) {
                return;
            }
            if (draft.targetNodeId === undefined || draft.targetPortId === undefined) {
                return "invalid";
            }
            return this.getConnectionCandidateValidity({
                id: "flow-connection-draft",
                sourceNodeId: nodeId,
                sourcePortId: portId,
                targetNodeId: draft.targetNodeId,
                targetPortId: draft.targetPortId,
            }).valid
                ? "valid"
                : "invalid";
        }
        if (draft.targetNodeId !== nodeId || draft.targetPortId !== portId) {
            return;
        }
        return this.getConnectionCandidateValidity({
            id: "flow-connection-draft",
            sourceNodeId: draft.sourceNodeId,
            sourcePortId: draft.sourcePortId,
            targetNodeId: nodeId,
            targetPortId: portId,
        }).valid
            ? "valid"
            : "invalid";
    }

    /**
     * @param {{ clientX: number, clientY: number }} ev
     * @returns {import("./flow_types").FlowPosition}
     */
    toWorld(ev) {
        const canvasRect = this.canvasEl?.getBoundingClientRect() ?? {
            left: 0,
            top: 0,
        };
        return screenToWorld(
            { x: ev.clientX, y: ev.clientY },
            canvasRect,
            this.store.viewport,
        );
    }

    /** @param {PointerEvent} ev */
    onCanvasPointerDown(ev) {
        const target = /** @type {HTMLElement | null} */ (ev.target);
        if (
            (ev.button !== 0 && ev.button !== 1) ||
            target?.closest(
                ".o_flow_editor_node, .o_flow_editor_connection, .o_flow_editor_controls, .o_flow_editor_location_indicator",
            )
        ) {
            return;
        }
        ev.preventDefault();
        this.cancelViewportAnimation();
        this.focusCanvas();
        this.clearSelection();
        if (!this.store.startInteraction({ type: "pan" })) {
            return;
        }
        this.framed = false;
        this.activePointerId = ev.pointerId;
        this.pointerStart = { x: ev.clientX, y: ev.clientY };
        this.panOrigin = { ...this.store.viewport };
        this.props.onPan({ phase: "start" });
    }

    /** @param {import("./flow_node").FlowNodeEventParams} params */
    onNodePointerDown({ node, originalEvent }) {
        const pointerEvent = /** @type {PointerEvent} */ (originalEvent);
        if (pointerEvent.button !== 0) {
            return;
        }
        pointerEvent.preventDefault();
        pointerEvent.stopPropagation();
        this.focusCanvas();
        const pointer = this.toWorld(pointerEvent);
        if (
            !this.store.startInteraction({
                type: "node_drag",
                nodeId: node.id,
                origin: { ...node.position },
            })
        ) {
            return;
        }
        this.selectNode(node.id);
        this.activePointerId = pointerEvent.pointerId;
        this.pointerStart = { x: pointerEvent.clientX, y: pointerEvent.clientY };
        this.dragOffset = {
            x: pointer.x - node.position.x,
            y: pointer.y - node.position.y,
        };
        this.snapNodeDrag = pointerEvent.altKey;
        this.didDrag = false;
        this.props.onDrag({
            phase: "start",
            node,
            position: { ...node.position },
            originalEvent: pointerEvent,
        });
    }

    /** @param {import("./flow_port").FlowPortPointerDownParams} params */
    async onPortPointerDown({ nodeId, port, originalEvent }) {
        if (
            originalEvent.button !== 0 ||
            this.store.readonly ||
            this.store.interaction
        ) {
            return;
        }
        originalEvent.preventDefault();
        this.focusCanvas();
        let sourceNodeId = nodeId;
        let sourcePortId = port.id;
        let connection;
        let reconnectSource = false;
        let targetNodeId;
        let targetPortId;
        if (port.direction === "input") {
            connection = this.lastConnectionAt(
                (candidate) =>
                    candidate.targetNodeId === nodeId &&
                    candidate.targetPortId === port.id,
            );
            if (connection) {
                sourceNodeId = connection.sourceNodeId;
                sourcePortId = connection.sourcePortId;
            } else {
                reconnectSource = true;
                targetNodeId = nodeId;
                targetPortId = port.id;
            }
        } else {
            connection = this.lastConnectionAt(
                (candidate) =>
                    candidate.sourceNodeId === nodeId &&
                    candidate.sourcePortId === port.id,
            );
            if (connection) {
                reconnectSource = true;
                targetNodeId = connection.targetNodeId;
                targetPortId = connection.targetPortId;
            }
        }
        const pointer = this.toWorld(originalEvent);
        if (
            !this.store.startInteraction({
                type: "connection_drag",
                connectionDraft: {
                    sourceNodeId,
                    sourcePortId,
                    pointer,
                    ...(reconnectSource
                        ? {
                              reconnectSource: true,
                              targetNodeId,
                              targetPortId,
                          }
                        : {}),
                    ...(connection ? { pendingConnectionId: connection.id } : {}),
                },
            })
        ) {
            return;
        }
        this.activePointerId = originalEvent.pointerId;
        this.pointerStart = { x: originalEvent.clientX, y: originalEvent.clientY };
    }

    /**
     * @param {import("./flow_types").FlowConnectionDraft} draft
     * @returns {Promise<boolean>}
     */
    async detachPendingConnection(draft) {
        const connectionId = draft.pendingConnectionId;
        delete draft.pendingConnectionId;
        const connection =
            connectionId === undefined
                ? undefined
                : this.store.getConnection(connectionId);
        if (!connection) {
            return true;
        }
        if ((await this.props.onDisconnect({ connection })) === false) {
            const interaction = this.store.interaction;
            if (
                interaction?.type === "connection_drag" &&
                interaction.connectionDraft === draft
            ) {
                this.store.cancelInteraction();
                this.resetPointerState();
            }
            return false;
        }
        this.store.removeConnection(connection.id);
        return true;
    }

    /**
     * @param {(connection: import("./flow_types").FlowConnection) => boolean} predicate
     * @returns {import("./flow_types").FlowConnection | undefined}
     */
    lastConnectionAt(predicate) {
        return this.store.connections
            .filter(predicate)
            .sort((connectionA, connectionB) =>
                String(connectionA.id).localeCompare(
                    String(connectionB.id),
                    undefined,
                    {
                        numeric: true,
                    },
                ),
            )
            .at(-1);
    }

    /** @param {import("./flow_node").FlowNodeEventParams} params */
    onResizePointerDown({ node, originalEvent }) {
        const pointerEvent = /** @type {PointerEvent} */ (originalEvent);
        if (
            pointerEvent.button !== 0 ||
            node.shape === "circle" ||
            node.resizable === false
        ) {
            return;
        }
        pointerEvent.preventDefault();
        this.focusCanvas();
        const size = getNodeSize(node, this.props.defaultNodeSize);
        if (
            !this.store.startInteraction({
                type: "node_resize",
                nodeId: node.id,
                origin: { ...size },
            })
        ) {
            return;
        }
        this.selectNode(node.id);
        this.activePointerId = pointerEvent.pointerId;
        this.pointerStart = { x: pointerEvent.clientX, y: pointerEvent.clientY };
        this.props.onResize({
            phase: "start",
            node,
            size: { ...size },
            originalEvent: pointerEvent,
        });
    }

    /** @param {PointerEvent} ev */
    onPointerMove(ev) {
        const interaction = this.store.interaction;
        if (ev.pointerId !== this.activePointerId || !interaction) {
            return;
        }
        ev.preventDefault();
        if (interaction.type === "node_drag") {
            const pointer = this.toWorld(ev);
            const position = {
                x: pointer.x - this.dragOffset.x,
                y: pointer.y - this.dragOffset.y,
            };
            if (this.snapNodeDrag) {
                const gridSize = Math.max(this.props.gridSize, 1);
                position.x = Math.round(position.x / gridSize) * gridSize;
                position.y = Math.round(position.y / gridSize) * gridSize;
            }
            this.didDrag ||=
                Math.hypot(
                    ev.clientX - this.pointerStart.x,
                    ev.clientY - this.pointerStart.y,
                ) > 3;
            if (this.store.moveNode(interaction.nodeId, position)) {
                this.props.onDrag({
                    phase: "move",
                    node: this.store.getNode(interaction.nodeId),
                    position,
                    originalEvent: ev,
                });
            }
        } else if (interaction.type === "node_resize") {
            const { nodeId, origin } = interaction;
            const scale = this.store.viewport.scale;
            const size = {
                width: this.clampNodeSide(
                    "width",
                    origin.width + (ev.clientX - this.pointerStart.x) / scale,
                ),
                height: this.clampNodeSide(
                    "height",
                    origin.height + (ev.clientY - this.pointerStart.y) / scale,
                ),
            };
            if (this.store.resizeNode(nodeId, size)) {
                this.props.onResize({
                    phase: "move",
                    node: this.store.getNode(nodeId),
                    size,
                    originalEvent: ev,
                });
            }
        } else if (interaction.type === "connection_drag") {
            const draft = interaction.connectionDraft;
            if (draft.pendingConnectionId !== undefined) {
                const travelled = Math.hypot(
                    ev.clientX - this.pointerStart.x,
                    ev.clientY - this.pointerStart.y,
                );
                if (travelled <= DRAG_THRESHOLD) {
                    return;
                }
                this.pendingDetach ??= this.detachPendingConnection(draft);
            }
            const target = interaction.connectionDraft.reconnectSource
                ? this.getOutputPortAtPoint(ev.clientX, ev.clientY)
                : this.getInputPortAtPoint(ev.clientX, ev.clientY);
            this.store.updateConnectionDraft(
                this.toWorld(ev),
                target
                    ? {
                          nodeId: target.node.id,
                          portId: target.portId,
                      }
                    : undefined,
            );
        } else {
            this.setViewport({
                x: this.panOrigin.x + ev.clientX - this.pointerStart.x,
                y: this.panOrigin.y + ev.clientY - this.pointerStart.y,
            });
        }
    }

    /**
     * @param {"width" | "height"} side
     * @param {number} value
     * @returns {number}
     */
    clampNodeSide(side, value) {
        return Math.min(
            this.props.maxNodeSize[side],
            Math.max(this.props.minNodeSize[side], value),
        );
    }

    /** @param {PointerEvent} ev */
    async onPointerUp(ev) {
        const interaction = this.store.interaction;
        if (ev.pointerId !== this.activePointerId || !interaction) {
            return;
        }
        if (interaction.type === "node_drag") {
            const node = this.store.getNode(interaction.nodeId);
            this.props.onDrag({
                phase: "end",
                node,
                position: { ...(node?.position ?? interaction.origin) },
                originalEvent: ev,
            });
            this.suppressNodeClick = this.didDrag;
            this.store.endInteraction();
        } else if (interaction.type === "node_resize") {
            const node = this.store.getNode(interaction.nodeId);
            this.props.onResize({
                phase: "end",
                node,
                size: node
                    ? getNodeSize(node, this.props.defaultNodeSize)
                    : interaction.origin,
                originalEvent: ev,
            });
            this.store.endInteraction();
        } else if (interaction.type === "connection_drag") {
            this.suppressNodeClick = true;
            const draft = interaction.connectionDraft;
            try {
                const detached = this.pendingDetach
                    ? await this.pendingDetach
                    : draft.pendingConnectionId === undefined;
                if (detached && this.store.interaction === interaction) {
                    await this.connectToPortAtPointer(draft, ev);
                }
            } finally {
                this.pendingDetach = null;
                if (this.store.interaction === interaction) {
                    this.store.endInteraction();
                }
                this.resetPointerState();
            }
            return;
        } else {
            this.store.endInteraction();
            if (interaction.type === "pan") {
                this.props.onPan({ phase: "end" });
            }
        }
        this.resetPointerState();
    }

    /** @param {FlowCancelEvent} ev */
    onPointerCancel(ev) {
        const interaction = this.store.interaction;
        if (ev.pointerId !== this.activePointerId || !interaction) {
            return;
        }
        const originalEvent = "originalEvent" in ev ? ev.originalEvent : ev;
        this.pendingDetach = null;
        this.store.cancelInteraction();
        this.notifyInteractionCancelled(interaction, originalEvent);
        this.resetPointerState();
    }

    /**
     * @param {import("./flow_types").FlowInteraction} interaction
     * @param {Event | null} originalEvent
     */
    notifyInteractionCancelled(interaction, originalEvent) {
        if (interaction.type === "node_drag") {
            this.props.onDrag({
                phase: "cancel",
                node: this.store.getNode(interaction.nodeId),
                position: { ...interaction.origin },
                originalEvent,
            });
        } else if (interaction.type === "node_resize") {
            this.props.onResize({
                phase: "cancel",
                node: this.store.getNode(interaction.nodeId),
                size: { ...interaction.origin },
                originalEvent,
            });
        } else if (interaction.type === "pan") {
            this.props.onPan({ phase: "cancel" });
        }
    }

    /**
     * @param {import("./flow_types").FlowConnectionDraft} draft
     * @param {PointerEvent} ev
     */
    async connectToPortAtPointer(draft, ev) {
        if (draft.reconnectSource) {
            const source = this.getOutputPortAtPoint(ev.clientX, ev.clientY);
            const targetNode =
                draft.targetNodeId === undefined
                    ? undefined
                    : this.store.getNode(draft.targetNodeId);
            if (source && targetNode && draft.targetPortId !== undefined) {
                await this.connectPorts(
                    {
                        sourceNodeId: source.node.id,
                        sourcePortId: source.portId,
                    },
                    {
                        node: targetNode,
                        portId: draft.targetPortId,
                    },
                );
            }
            return;
        }
        const target = this.getInputPortAtPoint(ev.clientX, ev.clientY);
        if (!target) {
            return;
        }
        await this.connectPorts(draft, target);
    }

    /**
     * @param {{ sourceNodeId: import("./flow_types").FlowNodeId, sourcePortId: import("./flow_types").FlowPortId }} draft
     * @param {{ node: import("./flow_types").FlowNode, portId: import("./flow_types").FlowPortId }} target
     */
    async connectPorts(draft, target) {
        const connection = {
            id: this.store.getNextConnectionId(),
            sourceNodeId: draft.sourceNodeId,
            sourcePortId: draft.sourcePortId,
            targetNodeId: target.node.id,
            targetPortId: target.portId,
        };
        const validation = this.getConnectionCandidateValidity(connection);
        if (!validation.valid) {
            this.props.onConnectionRejected({ connection, validation });
            return;
        }
        const result = await this.props.onConnect(connection);
        if (result !== false) {
            const persistedConnection =
                result && typeof result === "object" ? result : connection;
            const drawnByConsumer = Boolean(
                this.store.getConnection(persistedConnection.id) ||
                this.store.getConnection(connection.id),
            );
            log.logic("connect.persisted", () => ({
                candidateId: connection.id,
                persistedId: persistedConnection.id,
                drawnByConsumer,
            }));
            if (drawnByConsumer) {
                return;
            }
            const persistedValidation = this.getBuiltInValidity(persistedConnection);
            if (persistedValidation.valid) {
                this.store.addConnection(persistedConnection);
            } else {
                this.props.onConnectionRejected({
                    connection: persistedConnection,
                    validation: persistedValidation,
                });
            }
        }
    }

    /**
     * @param {number} clientX
     * @param {number} clientY
     * @param {import("./flow_types").FlowPortDirection} direction
     * @returns {{ node: import("./flow_types").FlowNode, portId: import("./flow_types").FlowPortId } | null}
     */
    getPortAtPoint(clientX, clientY, direction) {
        const portEl = document
            .elementFromPoint(clientX, clientY)
            ?.closest(`.o_flow_editor_port_${direction}`);
        if (!portEl || !this.canvasEl?.contains(portEl)) {
            return null;
        }
        const { nodeId, portId } = /** @type {HTMLElement} */ (portEl).dataset;
        if (portId === undefined) {
            return null;
        }
        const node = this.store.nodes.find(
            (candidate) => String(candidate.id) === nodeId,
        );
        const declared =
            direction === "input"
                ? node?.input?.id === portId
                : node?.outputs.some((output) => output.id === portId);
        return node && declared ? { node, portId } : null;
    }

    /**
     * @param {number} clientX
     * @param {number} clientY
     */
    getInputPortAtPoint(clientX, clientY) {
        return this.getPortAtPoint(clientX, clientY, "input");
    }

    /**
     * @param {number} clientX
     * @param {number} clientY
     */
    getOutputPortAtPoint(clientX, clientY) {
        return this.getPortAtPoint(clientX, clientY, "output");
    }

    /**
     * @param {import("./flow_types").FlowConnection} connection
     * @returns {import("./connection_validator").FlowConnectionValidation}
     */
    getConnectionCandidateValidity(connection) {
        const validation = this.getBuiltInValidity(connection);
        if (!validation.valid) {
            return validation;
        }
        return normalizeConnectionValidation(this.props.canConnect(connection));
    }

    /**
     * The editor's own rules, without the consumer's `canConnect`: once
     * `onConnect` has persisted a connection the consumer already counts it, so
     * asking `canConnect` again would reject every connection it just accepted.
     *
     * @param {import("./flow_types").FlowConnection} connection
     * @returns {import("./connection_validator").FlowConnectionValidation}
     */
    getBuiltInValidity(connection) {
        return getConnectionValidity(connection, {
            nodes: this.store.nodes,
            connections: this.store.connections,
            allowSelfConnections: this.props.allowSelfConnections,
        });
    }

    /** @param {WheelEvent} ev */
    onWheel(ev) {
        const canvasEl = this.canvasEl;
        if ((!ev.ctrlKey && !ev.metaKey) || !canvasEl) {
            return;
        }
        ev.preventDefault();
        this.cancelViewportAnimation();
        this.framed = false;
        const canvasRect = canvasEl.getBoundingClientRect();
        const pointer = screenToWorld(
            { x: ev.clientX, y: ev.clientY },
            canvasRect,
            this.store.viewport,
        );
        const scale = clampScale(
            this.store.viewport.scale * (ev.deltaY > 0 ? 0.9 : 1.1),
        );
        this.setViewport({
            x: ev.clientX - canvasRect.left - pointer.x * scale,
            y: ev.clientY - canvasRect.top - pointer.y * scale,
            scale,
        });
    }

    /** @param {number} factor */
    zoomBy(factor) {
        const canvasEl = this.canvasEl;
        if (!canvasEl) {
            return;
        }
        this.cancelViewportAnimation();
        this.framed = false;
        const canvasRect = canvasEl.getBoundingClientRect();
        const center = {
            x: canvasRect.left + canvasRect.width / 2,
            y: canvasRect.top + canvasRect.height / 2,
        };
        const worldCenter = screenToWorld(center, canvasRect, this.store.viewport);
        const scale = clampScale(this.store.viewport.scale * factor);
        this.setViewport({
            x: canvasRect.width / 2 - worldCenter.x * scale,
            y: canvasRect.height / 2 - worldCenter.y * scale,
            scale,
        });
    }

    zoomIn() {
        this.zoomBy(1.1);
    }

    zoomOut() {
        this.zoomBy(0.9);
    }

    onCanvasResize() {
        if (this.framed) {
            this.fitToContent();
        }
    }

    fitToContent() {
        const canvasEl = this.canvasEl;
        if (!canvasEl) {
            return;
        }
        this.cancelViewportAnimation();
        this.framed = true;
        const canvasRect = canvasEl.getBoundingClientRect();
        const bounds = this.flowBounds;
        if (!bounds || !canvasRect.width || !canvasRect.height) {
            this.setViewport({ x: 0, y: 0, scale: 1 });
            return;
        }
        const padding = 48;
        const width = Math.max(bounds.x2 - bounds.x1, 1);
        const height = Math.max(bounds.y2 - bounds.y1, 1);
        const scale = clampScale(
            Math.min(
                (canvasRect.width - padding * 2) / width,
                (canvasRect.height - padding * 2) / height,
                1,
            ),
        );
        this.setViewport({
            x: (canvasRect.width - width * scale) / 2 - bounds.x1 * scale,
            y: (canvasRect.height - height * scale) / 2 - bounds.y1 * scale,
            scale,
        });
    }

    /** @param {MouseEvent} ev */
    onFlowLocationClick(ev) {
        ev.stopPropagation();
        const target = this.flowCenter;
        const canvasEl = this.canvasEl;
        if (!target || !canvasEl) {
            return;
        }
        this.framed = false;
        const canvasRect = canvasEl.getBoundingClientRect();
        const scale = this.store.viewport.scale;
        this.animateViewportTo({
            x: canvasRect.width / 2 - target.x * scale,
            y: canvasRect.height / 2 - target.y * scale,
        });
    }

    /**
     * @param {{ x: number, y: number }} target
     * @param {number} [duration]
     */
    animateViewportTo(target, duration = 400) {
        this.cancelViewportAnimation();
        const start = { ...this.store.viewport };
        const delta = {
            x: target.x - start.x,
            y: target.y - start.y,
        };
        /** @type {number | undefined} */
        let startTime;
        /** @param {number} timestamp */
        const step = (timestamp) => {
            startTime ??= timestamp;
            const progress = Math.min(1, (timestamp - startTime) / duration);
            const eased =
                progress < 0.5 ? 2 * progress ** 2 : 1 - (-2 * progress + 2) ** 2 / 2;
            this.setViewport({
                x: start.x + delta.x * eased,
                y: start.y + delta.y * eased,
            });
            if (progress < 1) {
                this.viewportAnimationFrame = requestAnimationFrame(step);
            } else {
                this.viewportAnimationFrame = null;
            }
        };
        this.viewportAnimationFrame = requestAnimationFrame(step);
    }

    cancelViewportAnimation() {
        if (this.viewportAnimationFrame) {
            cancelAnimationFrame(this.viewportAnimationFrame);
            this.viewportAnimationFrame = null;
        }
    }

    /** @param {Partial<import("./flow_types").FlowViewport>} values */
    setViewport(values) {
        this.store.setViewport(values);
        this.props.onViewportChange({ ...this.store.viewport });
    }

    /** @param {import("./flow_node").FlowNodeEventParams} params */
    onNodeClick({ node, originalEvent }) {
        if (this.suppressNodeClick) {
            this.suppressNodeClick = false;
            return;
        }
        this.selectNode(node.id);
        this.props.onNodeClick({ node, originalEvent });
    }

    /** @param {import("./flow_connection").FlowConnectionClickParams} params */
    onConnectionClick({ connectionId }) {
        this.focusCanvas();
        this.store.setSelection({ connectionIds: [connectionId] });
        this.notifySelectionChange();
    }

    /** @param {import("./flow_types").FlowNodeId} nodeId */
    selectNode(nodeId) {
        this.store.setSelection({ nodeIds: [nodeId] });
        this.notifySelectionChange();
    }

    clearSelection() {
        this.store.clearSelection();
        this.notifySelectionChange();
    }

    notifySelectionChange() {
        this.props.onSelectionChange({
            nodeIds: [...this.store.selection.nodeIds],
            connectionIds: [...this.store.selection.connectionIds],
        });
    }

    /** @param {{ node: import("./flow_types").FlowNode }} params */
    async onNodeDeleteClick({ node }) {
        if (await this.deleteNode(node)) {
            this.notifySelectionChange();
        }
    }

    /**
     * @param {import("./flow_types").FlowNode | undefined} node
     * @returns {Promise<boolean>}
     */
    async deleteNode(node) {
        if (!node || this.store.readonly || node.readonly || node.deletable === false) {
            return false;
        }
        if (this.deletingNodeIds.has(node.id)) {
            log.logic("delete.skipped", () => ({
                nodeId: node.id,
                deletionPending: true,
            }));
            return false;
        }
        this.deletingNodeIds.add(node.id);
        try {
            if ((await this.props.onNodeDelete({ node })) === false) {
                log.logic("delete.vetoed", () => ({
                    nodeId: node.id,
                    by: "onNodeDelete",
                }));
                return false;
            }
        } finally {
            this.deletingNodeIds.delete(node.id);
        }
        log.logic("delete.node", () => ({
            nodeId: node.id,
            droppedConnectionIds: this.store.connections
                .filter(
                    (connection) =>
                        connection.sourceNodeId === node.id ||
                        connection.targetNodeId === node.id,
                )
                .map((connection) => connection.id),
        }));
        this.store.removeNode(node.id);
        return true;
    }

    /** @param {KeyboardEvent} ev */
    async onKeyDown(ev) {
        if (!this.canvasEl?.contains(document.activeElement)) {
            return;
        }
        if (ev.key === "Escape" && this.store.interaction) {
            ev.preventDefault();
            this.onPointerCancel({
                pointerId: this.activePointerId,
                originalEvent: ev,
            });
            return;
        }
        const activeTag = document.activeElement?.tagName;
        if (
            this.store.readonly ||
            (ev.key !== "Delete" && ev.key !== "Backspace") ||
            (activeTag !== undefined && ["INPUT", "TEXTAREA"].includes(activeTag))
        ) {
            return;
        }
        ev.preventDefault();
        if (ev.repeat || this.deletingSelection) {
            log.logic("delete.skipped", () => ({
                repeat: ev.repeat,
                deletionPending: this.deletingSelection,
            }));
            return;
        }
        const connectionIds = [...this.store.selection.connectionIds];
        const nodeIds = [...this.store.selection.nodeIds];
        this.deletingSelection = true;
        try {
            for (const nodeId of nodeIds) {
                await this.deleteNode(this.store.getNode(nodeId));
            }
            for (const connectionId of connectionIds) {
                const connection = this.store.getConnection(connectionId);
                if (!connection) {
                    log.logic("delete.connection_gone", () => ({ connectionId }));
                    continue;
                }
                if ((await this.props.onDisconnect({ connection })) !== false) {
                    this.store.removeConnection(connectionId);
                }
            }
        } finally {
            this.deletingSelection = false;
        }
        this.notifySelectionChange();
    }

    resetPointerState() {
        this.activePointerId = null;
        this.pointerStart = { x: 0, y: 0 };
        this.panOrigin = { x: 0, y: 0, scale: 1 };
        this.dragOffset = { x: 0, y: 0 };
        this.didDrag = false;
        this.snapNodeDrag = false;
    }

    /**
     * @param {import("./flow_types").FlowNodeId} nodeId
     * @returns {boolean}
     */
    isNodeSelected(nodeId) {
        return this.store.selection.nodeIds.includes(nodeId);
    }

    /**
     * @param {import("./flow_types").FlowConnectionId} connectionId
     * @returns {boolean}
     */
    isConnectionSelected(connectionId) {
        return this.store.selection.connectionIds.includes(connectionId);
    }
}
