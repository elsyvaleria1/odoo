// @ts-check
/** @odoo-module native */

import { toRaw } from "@odoo/owl";

import { DEFAULT_FLOW_VIEWPORT } from "./flow_types.js";
import { clampScale } from "./geometry/coordinates.js";

/**
 * @param {import("./flow_types").FlowNode} node
 * @returns {import("./flow_types").FlowNode}
 */
function copyNode(node) {
    return {
        ...node,
        position: { ...node.position },
        ...(node.size ? { size: { ...node.size } } : {}),
        ...(node.record
            ? { record: { ...node.record, data: { ...node.record.data } } }
            : {}),
        ...(node.input ? { input: { ...node.input } } : {}),
        outputs: node.outputs.map((output) => ({ ...output })),
    };
}

/**
 * @param {import("./flow_types").FlowConnection} connection
 * @returns {import("./flow_types").FlowConnection}
 */
function copyConnection(connection) {
    return { ...connection };
}

/**
 * @template {{ id: string | number }} T
 * @param {T[]} current
 * @param {T[]} next
 * @param {T[]} previous
 * @param {(item: T) => T} copy
 * @returns {{ items: T[], localIds: Set<string | number> }}
 */
function mergeById(current, next, previous, copy) {
    const previousById = new Map(previous.map((item) => [item.id, toRaw(item)]));
    const currentById = new Map(current.map((item) => [item.id, item]));
    const nextIds = new Set();
    const items = [];
    for (const item of next) {
        nextIds.add(item.id);
        if (previousById.get(item.id) === toRaw(item)) {
            const local = currentById.get(item.id);
            if (local) {
                items.push(local);
            }
        } else {
            items.push(copy(item));
        }
    }
    const localIds = new Set();
    for (const item of current) {
        if (!nextIds.has(item.id) && !previousById.has(item.id)) {
            items.push(item);
            localIds.add(item.id);
        }
    }
    return { items, localIds };
}

export class FlowEditorStore {
    /**
     * @param {Object} [params]
     * @param {import("./flow_types").FlowNode[]} [params.nodes]
     * @param {import("./flow_types").FlowConnection[]} [params.connections]
     * @param {import("./flow_types").FlowViewport | null} [params.viewport]
     * @param {boolean} [params.readonly]
     */
    constructor({
        nodes = [],
        connections = [],
        viewport = DEFAULT_FLOW_VIEWPORT,
        readonly = false,
    } = {}) {
        const initialViewport = viewport ?? DEFAULT_FLOW_VIEWPORT;
        this.nodes = nodes.map(copyNode);
        this.connections = connections.map(copyConnection);
        /** @type {Map<import("./flow_types").FlowNodeId, import("./flow_types").FlowNode>} */
        this.nodeIndex = new Map();
        /** @type {Map<import("./flow_types").FlowConnectionId, import("./flow_types").FlowConnection>} */
        this.connectionIndex = new Map();
        this._reindexNodes();
        this._reindexConnections();
        this.viewport = {
            x: initialViewport.x,
            y: initialViewport.y,
            scale: clampScale(initialViewport.scale),
        };
        /** @type {import("./flow_types").FlowSelection} */
        this.selection = {
            nodeIds: [],
            connectionIds: [],
        };
        /** @type {import("./flow_types").FlowInteraction | null} */
        this.interaction = null;
        this.readonly = readonly;
        this.connectionSequence = 1;
    }

    /**
     * @param {Object} graph
     * @param {import("./flow_types").FlowNode[]} graph.nodes
     * @param {import("./flow_types").FlowConnection[]} graph.connections
     * @param {Object} [previous]
     * @param {import("./flow_types").FlowNode[]} previous.nodes
     * @param {import("./flow_types").FlowConnection[]} previous.connections
     * @returns {import("./flow_types").FlowInteraction | null}
     */
    setGraph(
        { nodes, connections },
        previous = { nodes: this.nodes, connections: this.connections },
    ) {
        this.nodes = mergeById(this.nodes, nodes, previous.nodes, copyNode).items;
        this._reindexNodes();
        const merged = mergeById(
            this.connections,
            connections,
            previous.connections,
            copyConnection,
        );
        this.connections = merged.items.filter(
            (connection) =>
                !merged.localIds.has(connection.id) ||
                (this.nodeIndex.has(connection.sourceNodeId) &&
                    this.nodeIndex.has(connection.targetNodeId)),
        );
        this._reindexConnections();
        this._removeMissingItemsFromSelection();
        const interaction = this.interaction;
        if (!interaction || this._isInteractionValid(interaction)) {
            return null;
        }
        this.interaction = null;
        return interaction;
    }

    /**
     * @param {import("./flow_types").FlowInteraction} interaction
     * @returns {boolean}
     */
    _isInteractionValid(interaction) {
        if (interaction.type === "node_drag" || interaction.type === "node_resize") {
            return this.nodeIndex.has(interaction.nodeId);
        }
        if (interaction.type === "connection_drag") {
            const draft = interaction.connectionDraft;
            const hasOutput = this.getNode(draft.sourceNodeId)?.outputs.some(
                (port) => port.id === draft.sourcePortId,
            );
            if (!draft.reconnectSource || draft.targetNodeId === undefined) {
                return Boolean(hasOutput);
            }
            return this.getNode(draft.targetNodeId)?.input?.id === draft.targetPortId;
        }
        return true;
    }

    /**
     * @param {import("./flow_types").FlowNodeId} nodeId
     * @returns {import("./flow_types").FlowNode | undefined}
     */
    getNode(nodeId) {
        return this.nodeIndex.get(nodeId);
    }

    /**
     * @param {import("./flow_types").FlowConnectionId} connectionId
     * @returns {import("./flow_types").FlowConnection | undefined}
     */
    getConnection(connectionId) {
        return this.connectionIndex.get(connectionId);
    }

    /** @returns {import("./flow_types").FlowConnectionId} */
    getNextConnectionId() {
        let connectionId;
        do {
            connectionId = `flow-connection-${this.connectionSequence++}`;
        } while (this.getConnection(connectionId));
        return connectionId;
    }

    /**
     * @param {import("./flow_types").FlowNode} node
     * @returns {boolean}
     */
    addNode(node) {
        if (this.readonly || this.getNode(node.id)) {
            return false;
        }
        const copy = copyNode(node);
        this.nodes.push(copy);
        this.nodeIndex.set(copy.id, copy);
        return true;
    }

    /**
     * @param {import("./flow_types").FlowNodeId} nodeId
     * @param {Partial<import("./flow_types").FlowNode>} values
     * @returns {boolean}
     */
    updateNode(nodeId, values) {
        const nodeIndex = this.nodes.findIndex((node) => node.id === nodeId);
        const node = this.nodes[nodeIndex];
        if (this.readonly || !node || node.readonly) {
            return false;
        }
        const updated = copyNode({
            ...node,
            ...values,
            position: values.position || node.position,
            input: Object.hasOwn(values, "input") ? values.input : node.input,
            outputs: values.outputs || node.outputs,
        });
        this.nodes[nodeIndex] = updated;
        this.nodeIndex.set(updated.id, updated);
        return true;
    }

    /**
     * @param {import("./flow_types").FlowNodeId} nodeId
     * @param {import("./flow_types").FlowPosition} position
     * @returns {boolean}
     */
    moveNode(nodeId, position) {
        return this.updateNode(nodeId, { position });
    }

    /**
     * @param {import("./flow_types").FlowNodeId} nodeId
     * @param {import("./flow_types").FlowSize} size
     * @returns {boolean}
     */
    resizeNode(nodeId, size) {
        return this.updateNode(nodeId, { size });
    }

    /**
     * @param {import("./flow_types").FlowNodeId} nodeId
     * @returns {boolean}
     */
    removeNode(nodeId) {
        const node = this.getNode(nodeId);
        if (this.readonly || !node || node.readonly || node.deletable === false) {
            return false;
        }
        this.nodes = this.nodes.filter((candidate) => candidate.id !== nodeId);
        this.nodeIndex.delete(nodeId);
        this.connections = this.connections.filter(
            (connection) =>
                connection.sourceNodeId !== nodeId &&
                connection.targetNodeId !== nodeId,
        );
        this._reindexConnections();
        this._removeMissingItemsFromSelection();
        return true;
    }

    /**
     * @param {import("./flow_types").FlowConnection} connection
     * @returns {boolean}
     */
    addConnection(connection) {
        if (this.readonly || this.getConnection(connection.id)) {
            return false;
        }
        const copy = copyConnection(connection);
        this.connections.push(copy);
        this.connectionIndex.set(copy.id, copy);
        return true;
    }

    /**
     * @param {import("./flow_types").FlowConnectionId} connectionId
     * @returns {boolean}
     */
    removeConnection(connectionId) {
        if (this.readonly || !this.getConnection(connectionId)) {
            return false;
        }
        this.connections = this.connections.filter(
            (connection) => connection.id !== connectionId,
        );
        this.connectionIndex.delete(connectionId);
        this._removeMissingItemsFromSelection();
        return true;
    }

    /** @param {Partial<import("./flow_types").FlowSelection>} selection */
    setSelection({ nodeIds = [], connectionIds = [] }) {
        this.selection.nodeIds = [...new Set(nodeIds)].filter((id) =>
            this.nodeIndex.has(id),
        );
        this.selection.connectionIds = [...new Set(connectionIds)].filter((id) =>
            this.connectionIndex.has(id),
        );
    }

    clearSelection() {
        this.selection.nodeIds = [];
        this.selection.connectionIds = [];
    }

    /** @param {Partial<import("./flow_types").FlowViewport>} values */
    setViewport(values) {
        this.viewport = {
            ...this.viewport,
            ...values,
            scale: clampScale(values.scale ?? this.viewport.scale),
        };
    }

    /** @param {boolean} readonly */
    setReadonly(readonly) {
        if (readonly && this.interaction?.type !== "pan") {
            this.cancelInteraction();
        }
        this.readonly = readonly;
    }

    /**
     * @param {import("./flow_types").FlowInteraction} interaction
     * @returns {boolean}
     */
    startInteraction(interaction) {
        if (this.interaction || (this.readonly && interaction.type !== "pan")) {
            return false;
        }
        if (interaction.type === "node_drag" || interaction.type === "node_resize") {
            const node = this.getNode(interaction.nodeId);
            if (!node || node.readonly) {
                return false;
            }
            this.interaction = /** @type {import("./flow_types").FlowInteraction} */ ({
                ...interaction,
                origin: { ...interaction.origin },
            });
        } else if (interaction.type === "connection_drag") {
            this.interaction = {
                ...interaction,
                connectionDraft: {
                    ...interaction.connectionDraft,
                    pointer: { ...interaction.connectionDraft.pointer },
                },
            };
        } else {
            this.interaction = { ...interaction };
        }
        return true;
    }

    /**
     * @param {import("./flow_types").FlowPosition} pointer
     * @param {Object} [target]
     * @param {import("./flow_types").FlowNodeId} [target.nodeId]
     * @param {import("./flow_types").FlowPortId} [target.portId]
     */
    updateConnectionDraft(pointer, target = {}) {
        if (this.interaction?.type === "connection_drag") {
            const draft = this.interaction.connectionDraft;
            Object.assign(
                draft,
                draft.reconnectSource
                    ? {
                          pointer,
                          sourceCandidateNodeId: target.nodeId,
                          sourceCandidatePortId: target.portId,
                      }
                    : {
                          pointer,
                          targetNodeId: target.nodeId,
                          targetPortId: target.portId,
                      },
            );
        }
    }

    endInteraction() {
        this.interaction = null;
    }

    cancelInteraction() {
        const interaction = this.interaction;
        if (interaction?.type === "node_drag") {
            this.moveNode(interaction.nodeId, interaction.origin);
        } else if (interaction?.type === "node_resize") {
            this.resizeNode(interaction.nodeId, interaction.origin);
        }
        this.interaction = null;
    }

    _reindexNodes() {
        this.nodeIndex = new Map(this.nodes.map((node) => [node.id, node]));
    }

    _reindexConnections() {
        this.connectionIndex = new Map(
            this.connections.map((connection) => [connection.id, connection]),
        );
    }

    _removeMissingItemsFromSelection() {
        this.selection.nodeIds = this.selection.nodeIds.filter((id) =>
            this.nodeIndex.has(id),
        );
        this.selection.connectionIds = this.selection.connectionIds.filter((id) =>
            this.connectionIndex.has(id),
        );
    }
}
