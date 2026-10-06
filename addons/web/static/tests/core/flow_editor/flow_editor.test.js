// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { advanceFrame, advanceTime, animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, toRaw, useProps, xml } from "@odoo/owl";
import { mountWithCleanup, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { FlowEditor } from "@web/core/flow_editor/flow_editor";
import { FlowEditorStore } from "@web/core/flow_editor/flow_editor_store";
import { Deferred } from "@web/core/utils/concurrency";
import { patch } from "@web/core/utils/patch";

describe.current.tags("headless");

const DEFAULT_NODE_SIZE = { width: 220, height: 120 };
const MIN_NODE_SIZE = { width: 120, height: 80 };
const MAX_NODE_SIZE = { width: 640, height: 480 };

/**
 * @param {import("@web/core/flow_editor/flow_types").FlowNodeId} id
 * @param {Partial<import("@web/core/flow_editor/flow_types").FlowNode>} [overrides]
 * @returns {import("@web/core/flow_editor/flow_types").FlowNode}
 */
function node(id, overrides = {}) {
    return {
        id,
        type: "test",
        position: { x: 0, y: 0 },
        outputs: [],
        ...overrides,
    };
}

/**
 * @param {import("@web/core/flow_editor/flow_types").FlowConnectionId} id
 * @param {import("@web/core/flow_editor/flow_types").FlowNodeId} sourceNodeId
 * @param {import("@web/core/flow_editor/flow_types").FlowNodeId} targetNodeId
 * @param {Partial<import("@web/core/flow_editor/flow_types").FlowConnection>} [overrides]
 * @returns {import("@web/core/flow_editor/flow_types").FlowConnection}
 */
function connection(id, sourceNodeId, targetNodeId, overrides = {}) {
    return {
        id,
        sourceNodeId,
        sourcePortId: "output",
        targetNodeId,
        targetPortId: "input",
        ...overrides,
    };
}

function pointerEvent(overrides = {}) {
    return {
        pointerId: 1,
        button: 0,
        clientX: 0,
        clientY: 0,
        altKey: false,
        target: { closest: /** @type {() => null} */ (() => null) },
        preventDefault: () => {},
        stopPropagation: () => {},
        ...overrides,
    };
}

function wheelEvent(overrides = {}) {
    return {
        ctrlKey: true,
        metaKey: false,
        deltaY: -1,
        clientX: 0,
        clientY: 0,
        preventDefault: () => {},
        ...overrides,
    };
}

/**
 * @param {any} element
 * @param {() => any} callback
 * @returns {any}
 */
function withElementFromPoint(element, callback) {
    const unpatch = patch(document, { elementFromPoint: () => element });
    let result;
    try {
        result = callback();
    } catch (error) {
        unpatch();
        throw error;
    }
    if (result && typeof result.then === "function") {
        return result.finally(unpatch);
    }
    unpatch();
    return result;
}

/**
 * @param {Object} params
 * @param {any} params.nodeId
 * @param {string} params.portId
 * @param {string} params.direction
 * @returns {any}
 */
function portElement({ nodeId, portId, direction }) {
    /** @type {any} */
    const el = {
        dataset: { nodeId, portId, portDirection: direction },
    };
    el.closest = (/** @type {string} */ selector) =>
        selector === `.o_flow_editor_port_${direction}` ? el : null;
    return el;
}

/**
 * @param {Object} [params]
 * @param {import("@web/core/flow_editor/flow_types").FlowNode[]} [params.nodes]
 * @param {import("@web/core/flow_editor/flow_types").FlowConnection[]} [params.connections]
 * @param {boolean} [params.readonly]
 * @param {Record<string, any>} [params.props]
 * @param {{ left: number, top: number, width: number, height: number }} [params.canvasRect]
 */
function makeEditor({
    nodes = [],
    connections = [],
    readonly = false,
    props = {},
    canvasRect = { left: 0, top: 0, width: 800, height: 600 },
} = {}) {
    const store = new FlowEditorStore({ nodes, connections, readonly });
    const canvasEl = {
        getBoundingClientRect: () => canvasRect,
        focus: () => {},
        contains: () => true,
    };
    return Object.assign(Object.create(FlowEditor.prototype), {
        canvasRef: { el: canvasEl },
        props: {
            nodes,
            connections,
            readonly,
            allowSelfConnections: false,
            canConnect: () => true,
            defaultNodeHeaderHeight: 32,
            defaultNodeSize: DEFAULT_NODE_SIZE,
            getConnectionClass: () => "",
            getConnectionLabel: () => "",
            gridSize: 20,
            maxNodeSize: MAX_NODE_SIZE,
            minNodeSize: MIN_NODE_SIZE,
            onConnect: (/** @type {any} */ candidate) => candidate,
            onConnectionRejected: () => {},
            onDisconnect: () => true,
            onDrag: () => {},
            onNodeClick: () => {},
            onNodeDelete: () => true,
            onPan: () => {},
            onResize: () => {},
            onSelectionChange: () => {},
            onViewportChange: () => {},
            ...props,
        },
        store,
        deletingNodeIds: new Set(),
    });
}

test("deletion vetoes do not prevent deleting other selected nodes", async () => {
    const protectedNode = node("protected");
    const deletable = node("deletable");
    const source = node("source");
    const target = node("target");
    const protectedConnection = connection(
        "protected-connection",
        source.id,
        target.id,
    );
    const leavesWithNode = connection("leaves-with-node", deletable.id, target.id);
    const survivesRefusal = connection("survives-refusal", protectedNode.id, target.id);
    const store = new FlowEditorStore({
        nodes: [protectedNode, deletable, source, target],
        connections: [protectedConnection, leavesWithNode, survivesRefusal],
    });
    store.setSelection({
        nodeIds: [protectedNode.id, deletable.id],
        connectionIds: [protectedConnection.id, leavesWithNode.id, survivesRefusal.id],
    });
    let selectionChangeCount = 0;
    let prevented = false;
    /** @type {any[]} */
    const askedToDelete = [];
    /** @type {any[]} */
    const askedToDisconnect = [];
    const editor = {
        canvasEl: { contains: () => true },
        deleteNode: FlowEditor.prototype.deleteNode,
        deletingNodeIds: new Set(),
        notifySelectionChange: () => selectionChangeCount++,
        props: {
            onDisconnect: (/** @type {any} */ payload) => {
                askedToDisconnect.push(payload.connection.id);
                return payload.connection.id !== protectedConnection.id;
            },
            onNodeDelete: (/** @type {any} */ payload) => {
                askedToDelete.push(payload.node.id);
                return payload.node.id !== protectedNode.id;
            },
        },
        store,
    };

    await FlowEditor.prototype.onKeyDown.call(
        editor,
        /** @type {KeyboardEvent} */ ({
            key: "Delete",
            preventDefault: () => {
                prevented = true;
            },
        }),
    );

    expect(prevented).toBe(true);
    expect(store.nodes.map(({ id }) => id)).toEqual([
        protectedNode.id,
        source.id,
        target.id,
    ]);
    expect(store.connections.map(({ id }) => id)).toEqual([protectedConnection.id]);
    expect(store.selection).toEqual({
        nodeIds: [protectedNode.id],
        connectionIds: [protectedConnection.id],
    });
    expect(selectionChangeCount).toBe(1);
    expect(askedToDelete).toEqual([protectedNode.id, deletable.id]);
    expect(askedToDisconnect).toEqual([protectedConnection.id, survivesRefusal.id], {
        message:
            "a selected connection that left with its node is not disconnected again; " +
            "one whose node refused is",
    });
});

describe("FlowEditor: deleting a node", () => {
    /**
     * @param {Record<string, any>} props
     */
    function makeChain(props) {
        return makeEditor({
            nodes: [node("a"), node("b"), node("c")],
            connections: [connection("ab", "a", "b"), connection("bc", "b", "c")],
            props,
        });
    }

    test("asks onNodeDelete alone and drops the node's connections locally", async () => {
        /** @type {string[]} */
        const calls = [];
        const editor = makeChain({
            onDisconnect: (/** @type {any} */ { connection: removed }) => {
                calls.push(`disconnect ${removed.id}`);
                return true;
            },
            onNodeDelete: (/** @type {any} */ { node: removed }) => {
                calls.push(`delete ${removed.id}`);
                return true;
            },
        });

        expect(await editor.deleteNode(editor.store.getNode("b"))).toBe(true);

        expect(calls).toEqual(["delete b"], {
            message:
                "the node's connections leave with it, without an onDisconnect each",
        });
        expect(editor.store.nodes.map(({ id }) => id)).toEqual(["a", "c"]);
        expect(editor.store.connections).toEqual([]);
    });

    test("a refused node deletion leaves the node and every connection in place", async () => {
        /** @type {string[]} */
        const calls = [];
        const editor = makeChain({
            onDisconnect: (/** @type {any} */ { connection: removed }) => {
                calls.push(`disconnect ${removed.id}`);
                return true;
            },
            onNodeDelete: (/** @type {any} */ { node: removed }) => {
                calls.push(`delete ${removed.id}`);
                return false;
            },
        });

        expect(await editor.deleteNode(editor.store.getNode("b"))).toBe(false);

        expect(calls).toEqual(["delete b"], {
            message: "no connection was committed away before the node was refused",
        });
        expect(editor.store.nodes.map(({ id }) => id)).toEqual(["a", "b", "c"]);
        expect(editor.store.connections.map(({ id }) => id)).toEqual(["ab", "bc"]);
    });

    test("a failing onNodeDelete releases the node for a later attempt", async () => {
        let attempts = 0;
        const editor = makeChain({
            onNodeDelete: async () => {
                attempts++;
                if (attempts === 1) {
                    throw new Error("network down");
                }
                return true;
            },
        });

        await expect(editor.deleteNode(editor.store.getNode("b"))).rejects.toThrow(
            "network down",
        );
        expect(await editor.deleteNode(editor.store.getNode("b"))).toBe(true);
        expect(attempts).toBe(2);
    });

    test("the delete button clicked again while the deletion is pending deletes once", async () => {
        const pending = new Deferred();
        /** @type {any[]} */
        const deleted = [];
        let selectionChangeCount = 0;
        const editor = makeChain({
            onNodeDelete: (/** @type {any} */ { node: removed }) => {
                deleted.push(removed.id);
                return pending;
            },
            onSelectionChange: () => selectionChangeCount++,
        });
        const b = editor.store.getNode("b");

        const clicks = [
            editor.onNodeDeleteClick({ node: b }),
            editor.onNodeDeleteClick({ node: b }),
        ];
        pending.resolve(true);
        await Promise.all(clicks);

        expect(deleted).toEqual(["b"]);
        expect(selectionChangeCount).toBe(1);
        expect(editor.store.getNode("b")).toBe(undefined);
    });

    test("a readonly editor never asks the consumer to delete a node", async () => {
        /** @type {any[]} */
        const deleted = [];
        const editor = makeEditor({
            nodes: [node("a")],
            readonly: true,
            props: {
                onNodeDelete: (/** @type {any} */ { node: removed }) => {
                    deleted.push(removed.id);
                    return true;
                },
            },
        });

        expect(await editor.deleteNode(editor.store.getNode("a"))).toBe(false);
        expect(deleted).toEqual([]);
    });
});

test("Delete pressed again or held while a deletion is pending deletes once", async () => {
    const store = new FlowEditorStore({
        nodes: [node("a"), node("b")],
        connections: [connection("c1", "a", "b")],
    });
    store.setSelection({ connectionIds: ["c1"] });
    const pending = new Deferred();
    /** @type {any[]} */
    const disconnected = [];
    const editor = {
        canvasEl: { contains: () => true },
        deleteNode: FlowEditor.prototype.deleteNode,
        deletingNodeIds: new Set(),
        notifySelectionChange: () => {},
        props: {
            onDisconnect: (/** @type {any} */ { connection: removed }) => {
                disconnected.push(removed.id);
                return pending;
            },
            onNodeDelete: () => true,
        },
        store,
    };
    const keydown = (/** @type {Partial<KeyboardEvent>} */ overrides = {}) =>
        FlowEditor.prototype.onKeyDown.call(
            editor,
            /** @type {KeyboardEvent} */ ({
                key: "Delete",
                preventDefault: () => {},
                ...overrides,
            }),
        );

    const presses = [keydown(), keydown(), keydown({ repeat: true })];
    pending.resolve(true);
    await Promise.all(presses);

    expect(disconnected).toEqual(["c1"]);
    expect(store.connections).toEqual([]);
    await keydown();
    expect(disconnected).toEqual(["c1"]);
});

describe("FlowEditor: canvas panning", () => {
    test("a pointerdown on empty canvas starts a pan that translates the viewport", () => {
        const editor = makeEditor();

        editor.onCanvasPointerDown(pointerEvent({ clientX: 100, clientY: 100 }));
        expect(editor.store.interaction).toEqual({ type: "pan" });

        editor.onPointerMove(pointerEvent({ clientX: 130, clientY: 150 }));
        expect(editor.store.viewport).toEqual({ x: 30, y: 50, scale: 1 });

        editor.onPointerUp(pointerEvent({ clientX: 130, clientY: 150 }));
        expect(editor.store.interaction).toBe(null);
    });

    test("a pointerdown on a node, connection or control does not start a pan", () => {
        const editor = makeEditor();

        editor.onCanvasPointerDown(pointerEvent({ target: { closest: () => ({}) } }));

        expect(editor.store.interaction).toBe(null);
    });

    test("a middle-button pointerdown also starts a pan, a right-button one does not", () => {
        const middleButton = makeEditor();
        middleButton.onCanvasPointerDown(pointerEvent({ button: 1 }));
        expect(middleButton.store.interaction).toEqual({ type: "pan" });

        const rightButton = makeEditor();
        rightButton.onCanvasPointerDown(pointerEvent({ button: 2 }));
        expect(rightButton.store.interaction).toBe(null);
    });

    test("readonly still allows panning", () => {
        const editor = makeEditor({ readonly: true });

        editor.onCanvasPointerDown(pointerEvent());

        expect(editor.store.interaction).toEqual({ type: "pan" });
    });
});

describe("FlowEditor: node dragging", () => {
    test("dragging a node moves it and reports every phase", () => {
        const draggedNode = node("a", { position: { x: 50, y: 60 } });
        const editor = makeEditor({ nodes: [draggedNode] });
        /** @type {any[]} */
        const phases = [];
        editor.props.onDrag = (/** @type {any} */ payload) =>
            phases.push(payload.phase);

        editor.onNodePointerDown({
            node: draggedNode,
            originalEvent: pointerEvent({ clientX: 100, clientY: 100 }),
        });
        expect(editor.store.interaction.type).toBe("node_drag");
        expect(editor.store.selection.nodeIds).toEqual(["a"]);

        editor.onPointerMove(pointerEvent({ clientX: 140, clientY: 150 }));
        expect(editor.store.getNode("a").position).toEqual({ x: 90, y: 110 });

        editor.onPointerUp(pointerEvent({ clientX: 140, clientY: 150 }));

        expect(phases).toEqual(["start", "move", "end"]);
        expect(editor.store.interaction).toBe(null);
        expect(editor.suppressNodeClick).toBe(true);
    });

    test("holding alt snaps the dragged position to the grid", () => {
        const draggedNode = node("a", { position: { x: 0, y: 0 } });
        const editor = makeEditor({ nodes: [draggedNode] });

        editor.onNodePointerDown({
            node: draggedNode,
            originalEvent: pointerEvent({ clientX: 0, clientY: 0, altKey: true }),
        });
        editor.onPointerMove(pointerEvent({ clientX: 34, clientY: 6 }));

        expect(editor.store.getNode("a").position).toEqual({ x: 40, y: 0 });
    });

    test("a click without prior movement does not suppress the next node click", () => {
        const draggedNode = node("a");
        const editor = makeEditor({ nodes: [draggedNode] });

        editor.onNodePointerDown({ node: draggedNode, originalEvent: pointerEvent() });
        editor.onPointerUp(pointerEvent());

        expect(editor.suppressNodeClick).toBe(false);
    });

    test("dragging a readonly node is not allowed to start", () => {
        const readonlyNode = node("a", { readonly: true });
        const editor = makeEditor({ nodes: [readonlyNode] });

        editor.onNodePointerDown({ node: readonlyNode, originalEvent: pointerEvent() });

        expect(editor.store.interaction).toBe(null);
    });
});

describe("FlowEditor: node resizing", () => {
    test("resizing a node reports every phase and respects the minimum size", () => {
        const resizedNode = node("a");
        const editor = makeEditor({ nodes: [resizedNode] });
        /** @type {any[]} */
        const phases = [];
        editor.props.onResize = (/** @type {any} */ payload) =>
            phases.push({ phase: payload.phase, size: payload.size });

        editor.onResizePointerDown({
            node: resizedNode,
            originalEvent: pointerEvent({ clientX: 200, clientY: 200 }),
        });
        expect(editor.store.interaction.origin).toEqual(DEFAULT_NODE_SIZE);

        editor.onPointerMove(pointerEvent({ clientX: 260, clientY: 170 }));
        expect(editor.store.getNode("a").size).toEqual({ width: 280, height: 90 });

        editor.onPointerUp(pointerEvent({ clientX: 260, clientY: 170 }));

        expect(phases.map((entry) => entry.phase)).toEqual(["start", "move", "end"]);
        expect(phases.at(-1).size).toEqual({ width: 280, height: 90 });
    });

    test("resizing a node respects the maximum size", () => {
        const resizedNode = node("a");
        const editor = makeEditor({ nodes: [resizedNode] });

        editor.onResizePointerDown({
            node: resizedNode,
            originalEvent: pointerEvent({ clientX: 0, clientY: 0 }),
        });
        editor.onPointerMove(pointerEvent({ clientX: 5000, clientY: 5000 }));

        expect(editor.store.getNode("a").size).toEqual(MAX_NODE_SIZE);
    });

    test("a circle-shaped node cannot be resized", () => {
        const circleNode = node("a", { shape: "circle" });
        const editor = makeEditor({ nodes: [circleNode] });

        editor.onResizePointerDown({ node: circleNode, originalEvent: pointerEvent() });

        expect(editor.store.interaction).toBe(null);
    });
});

describe("FlowEditor: zoom controls", () => {
    test("zoomIn increases the scale around the canvas center", () => {
        const editor = makeEditor();
        const scale = 1 * 1.1;

        editor.zoomIn();

        expect(editor.store.viewport).toEqual({
            x: 400 - 400 * scale,
            y: 300 - 300 * scale,
            scale,
        });
    });

    test("zoomOut decreases the scale around the canvas center", () => {
        const editor = makeEditor();
        const scale = 1 * 0.9;

        editor.zoomOut();

        expect(editor.store.viewport).toEqual({
            x: 400 - 400 * scale,
            y: 300 - 300 * scale,
            scale,
        });
    });

    test("ctrl+wheel zooms around the pointer position", () => {
        const editor = makeEditor();
        const scale = 1 * 1.1;

        editor.onWheel(wheelEvent({ clientX: 200, clientY: 100, deltaY: -1 }));

        expect(editor.store.viewport).toEqual({
            x: 200 - 200 * scale,
            y: 100 - 100 * scale,
            scale,
        });
    });

    test("wheel without a modifier key is ignored", () => {
        const editor = makeEditor();

        editor.onWheel(wheelEvent({ ctrlKey: false, metaKey: false }));

        expect(editor.store.viewport).toEqual({ x: 0, y: 0, scale: 1 });
    });
});

describe("FlowEditor: fit to content", () => {
    test("resets the viewport when there are no nodes", () => {
        const editor = makeEditor();
        editor.store.setViewport({ x: 500, y: 500, scale: 2 });

        editor.fitToContent();

        expect(editor.store.viewport).toEqual({ x: 0, y: 0, scale: 1 });
    });

    test("centers and scales the viewport to fit every node", () => {
        const editor = makeEditor({
            nodes: [
                node("a", {
                    position: { x: 0, y: 0 },
                    size: { width: 200, height: 100 },
                }),
                node("b", {
                    position: { x: 300, y: 400 },
                    size: { width: 100, height: 50 },
                }),
            ],
        });

        editor.fitToContent();

        expect(editor.store.viewport).toEqual({ x: 200, y: 75, scale: 1 });
    });
});

describe("FlowEditor: viewport animation", () => {
    test("setViewport reports the resulting viewport to the consumer", () => {
        /** @type {{x: number, y: number, scale: number}[]} */
        const seen = [];
        const editor = makeEditor({
            props: {
                onViewportChange: (
                    /** @type {{x: number, y: number, scale: number}} */ v,
                ) => seen.push({ ...v }),
            },
        });

        editor.setViewport({ x: 10, y: 20 });

        expect(seen).toEqual([{ x: 10, y: 20, scale: 1 }]);
    });

    test("clicking the location indicator animates the viewport toward the content", async () => {
        const editor = makeEditor({
            nodes: [node("far", { position: { x: 4000, y: 4000 } })],
        });
        expect(editor.store.viewport).toEqual({ x: 0, y: 0, scale: 1 });

        editor.onFlowLocationClick(pointerEvent());
        await advanceFrame();
        expect(editor.store.viewport).toEqual({ x: 0, y: 0, scale: 1 });

        await advanceTime(200);
        const halfway = { ...editor.store.viewport };
        expect(halfway.x).toBeLessThan(0);
        expect(halfway.y).toBeLessThan(0);
        expect(halfway.scale).toBe(1);

        await advanceTime(400);
        expect(editor.store.viewport.x).toBeLessThan(halfway.x);
        expect(editor.store.viewport.y).toBeLessThan(halfway.y);
    });

    test("cancelling the animation stops the viewport where it stood", async () => {
        const editor = makeEditor({
            nodes: [node("far", { position: { x: 4000, y: 4000 } })],
        });

        editor.onFlowLocationClick(pointerEvent());
        await advanceFrame();
        await advanceTime(200);
        const stopped = { ...editor.store.viewport };
        expect(stopped.x).toBeLessThan(0);

        editor.cancelViewportAnimation();
        await advanceTime(400);

        expect(editor.store.viewport).toEqual(stopped);
    });
});

describe("FlowEditor: connecting ports", () => {
    function makeConnectableEditor(overrides = {}) {
        return makeEditor({
            nodes: [
                node("a", {
                    position: { x: 0, y: 0 },
                    outputs: [{ id: "out", direction: "output", provides: "flow" }],
                }),
                node("b", {
                    position: { x: 300, y: 0 },
                    input: { id: "in", direction: "input", accepts: ["flow"] },
                }),
                node("c", {
                    position: { x: 150, y: 300 },
                    input: { id: "in", direction: "input", accepts: ["flow"] },
                }),
            ],
            ...overrides,
        });
    }

    test("dragging from an output port to an input port creates a connection", async () => {
        const editor = makeConnectableEditor();
        /** @type {any[]} */
        const connects = [];
        editor.props.onConnect = (/** @type {any} */ candidate) => {
            connects.push(candidate);
            return candidate;
        };

        editor.onPortPointerDown({
            nodeId: "a",
            port: { id: "out", direction: "output" },
            originalEvent: pointerEvent(),
        });
        expect(editor.store.interaction.type).toBe("connection_drag");

        const targetPort = portElement({
            nodeId: "b",
            portId: "in",
            direction: "input",
        });
        await withElementFromPoint(targetPort, () => {
            editor.onPointerMove(pointerEvent({ clientX: 310, clientY: 5 }));
            return editor.onPointerUp(pointerEvent({ clientX: 310, clientY: 5 }));
        });

        expect(editor.store.connections).toEqual([
            {
                id: "flow-connection-1",
                sourceNodeId: "a",
                sourcePortId: "out",
                targetNodeId: "b",
                targetPortId: "in",
            },
        ]);
        expect(connects.length).toBe(1);
        expect(editor.store.interaction).toBe(null);
    });

    test("a connection the consumer counts once persisted is kept, not rejected", async () => {
        /** @type {any[]} */
        const edges = [];
        const editor = makeConnectableEditor({
            props: {
                canConnect: (/** @type {any} */ candidate) =>
                    !edges.some((edge) => edge.targetNodeId === candidate.targetNodeId),
                onConnect: (/** @type {any} */ candidate) => {
                    edges.push(candidate);
                    return { ...candidate, id: 42 };
                },
            },
        });
        /** @type {any[]} */
        const rejections = [];
        editor.props.onConnectionRejected = (/** @type {any} */ payload) =>
            rejections.push(payload.validation.reason);

        editor.onPortPointerDown({
            nodeId: "a",
            port: { id: "out", direction: "output" },
            originalEvent: pointerEvent(),
        });
        const targetPort = portElement({
            nodeId: "b",
            portId: "in",
            direction: "input",
        });
        await withElementFromPoint(targetPort, () => {
            editor.onPointerMove(pointerEvent({ clientX: 310, clientY: 5 }));
            return editor.onPointerUp(pointerEvent({ clientX: 310, clientY: 5 }));
        });

        expect(rejections).toEqual([]);
        expect(editor.store.connections.map((/** @type {any} */ c) => c.id)).toEqual([
            42,
        ]);
    });

    test("a connection rejected by the consumer is not created", async () => {
        const editor = makeConnectableEditor({ props: { canConnect: () => false } });
        /** @type {any[]} */
        const rejections = [];
        editor.props.onConnectionRejected = (/** @type {any} */ payload) =>
            rejections.push(payload.validation.reason);
        /** @type {any[]} */
        const connects = [];
        editor.props.onConnect = (/** @type {any} */ candidate) => {
            connects.push(candidate);
            return candidate;
        };

        editor.onPortPointerDown({
            nodeId: "a",
            port: { id: "out", direction: "output" },
            originalEvent: pointerEvent(),
        });
        const targetPort = portElement({
            nodeId: "b",
            portId: "in",
            direction: "input",
        });
        await withElementFromPoint(targetPort, () => {
            editor.onPointerMove(pointerEvent({ clientX: 310, clientY: 5 }));
            return editor.onPointerUp(pointerEvent({ clientX: 310, clientY: 5 }));
        });

        expect(editor.store.connections).toEqual([]);
        expect(connects).toEqual([]);
        expect(rejections).toEqual(["consumer_rejected"]);
    });

    test("grabbing a connected input port reconnects it to a different node", async () => {
        const editor = makeConnectableEditor({
            connections: [
                connection("c1", "a", "b", { sourcePortId: "out", targetPortId: "in" }),
            ],
        });
        /** @type {any[]} */
        const disconnected = [];
        editor.props.onDisconnect = (/** @type {any} */ { connection: removed }) => {
            disconnected.push(removed.id);
            return true;
        };

        editor.onPortPointerDown({
            nodeId: "b",
            port: { id: "in", direction: "input" },
            originalEvent: pointerEvent(),
        });
        expect(disconnected).toEqual([]);
        expect(
            editor.store.connections.map((/** @type {{id: string}} */ c) => c.id),
        ).toEqual(["c1"]);
        expect(editor.draftConnectionGeometry).toBe(null);

        const targetPort = portElement({
            nodeId: "c",
            portId: "in",
            direction: "input",
        });
        await withElementFromPoint(targetPort, async () => {
            editor.onPointerMove(pointerEvent({ clientX: 155, clientY: 305 }));
            await editor.pendingDetach;
            expect(disconnected).toEqual(["c1"]);
            expect(editor.store.connections).toEqual([]);
            return editor.onPointerUp(pointerEvent({ clientX: 155, clientY: 305 }));
        });

        expect(editor.store.connections).toEqual([
            {
                id: "flow-connection-1",
                sourceNodeId: "a",
                sourcePortId: "out",
                targetNodeId: "c",
                targetPortId: "in",
            },
        ]);
    });

    test("vetoing the disconnection keeps the original connection", async () => {
        const editor = makeConnectableEditor({
            connections: [
                connection("c1", "a", "b", { sourcePortId: "out", targetPortId: "in" }),
            ],
            props: { onDisconnect: () => false },
        });

        editor.onPortPointerDown({
            nodeId: "b",
            port: { id: "in", direction: "input" },
            originalEvent: pointerEvent(),
        });
        editor.onPointerMove(pointerEvent({ clientX: 40, clientY: 0 }));
        await editor.pendingDetach;

        expect(
            editor.store.connections.map(
                (/** @type {any} */ candidate) => candidate.id,
            ),
        ).toEqual(["c1"]);
        expect(editor.store.interaction).toBe(null);
    });

    test("a click on a connected port, with no drag, keeps the connection", async () => {
        const editor = makeConnectableEditor({
            connections: [
                connection("c1", "a", "b", { sourcePortId: "out", targetPortId: "in" }),
            ],
        });
        /** @type {any[]} */
        const disconnected = [];
        editor.props.onDisconnect = (/** @type {any} */ { connection: removed }) => {
            disconnected.push(removed.id);
            return true;
        };

        for (const port of [
            { nodeId: "b", port: { id: "in", direction: "input" } },
            { nodeId: "a", port: { id: "out", direction: "output" } },
        ]) {
            editor.onPortPointerDown({ ...port, originalEvent: pointerEvent() });
            editor.onPointerMove(pointerEvent({ clientX: 2, clientY: 2 }));
            await withElementFromPoint(null, () =>
                editor.onPointerUp(pointerEvent({ clientX: 2, clientY: 2 })),
            );
            expect(editor.store.interaction).toBe(null);
        }

        expect(disconnected).toEqual([]);
        expect(
            editor.store.connections.map((/** @type {{id: string}} */ c) => c.id),
        ).toEqual(["c1"]);
    });

    test("connecting an output to its own node's input does not open the node afterward", async () => {
        const selfNode = node("a", {
            outputs: [{ id: "out", direction: "output", provides: "flow" }],
            input: { id: "in", direction: "input", accepts: ["flow"] },
        });
        const editor = makeEditor({
            nodes: [selfNode],
            props: { allowSelfConnections: true },
        });
        /** @type {any[]} */
        const clicks = [];
        editor.props.onNodeClick = (/** @type {any} */ payload) =>
            clicks.push(payload.node.id);

        editor.onPortPointerDown({
            nodeId: "a",
            port: { id: "out", direction: "output" },
            originalEvent: pointerEvent(),
        });
        const targetPort = portElement({
            nodeId: "a",
            portId: "in",
            direction: "input",
        });
        await withElementFromPoint(targetPort, () => {
            editor.onPointerMove(pointerEvent({ clientX: 10, clientY: 10 }));
            return editor.onPointerUp(pointerEvent({ clientX: 10, clientY: 10 }));
        });

        expect(editor.store.connections).toEqual([
            {
                id: "flow-connection-1",
                sourceNodeId: "a",
                sourcePortId: "out",
                targetNodeId: "a",
                targetPortId: "in",
            },
        ]);
        expect(editor.suppressNodeClick).toBe(true);

        editor.onNodeClick({ node: editor.store.getNode("a"), originalEvent: {} });
        expect(clicks).toEqual([]);
    });
});

describe("FlowEditor: connection labels", () => {
    test("a connection carries the label its consumer supplies", () => {
        const edge = connection("edge", "a", "b");
        const editor = makeEditor({
            nodes: [node("a"), node("b")],
            connections: [edge],
            props: {
                getConnectionLabel: (/** @type {any} */ c) =>
                    c.id === "edge" ? "only for large orders" : "",
            },
        });

        expect(editor.getConnectionLabel("edge")).toBe("only for large orders");
    });

    test("a consumer that supplies nothing leaves the connection unlabelled", () => {
        const editor = makeEditor({
            nodes: [node("a"), node("b")],
            connections: [connection("edge", "a", "b")],
            props: {
                getConnectionLabel: () => /** @type {string | undefined} */ (undefined),
            },
        });

        expect(editor.getConnectionLabel("edge")).toBe("");
    });

    test("an unknown connection resolves to no label rather than throwing", () => {
        const editor = makeEditor({
            props: {
                getConnectionLabel: () => {
                    throw new Error("must not be asked about an absent edge");
                },
            },
        });

        expect(editor.getConnectionLabel("nope")).toBe("");
    });
});

describe("FlowEditor: selection", () => {
    test("clicking a node selects it and notifies once", () => {
        const editor = makeEditor({ nodes: [node("a"), node("b")] });
        /** @type {any[]} */
        const clicks = [];
        editor.props.onNodeClick = (/** @type {any} */ payload) =>
            clicks.push(payload.node.id);
        let selectionChanges = 0;
        editor.props.onSelectionChange = () => selectionChanges++;

        editor.onNodeClick({ node: editor.store.getNode("a"), originalEvent: {} });

        expect(editor.store.selection.nodeIds).toEqual(["a"]);
        expect(editor.isNodeSelected("a")).toBe(true);
        expect(clicks).toEqual(["a"]);
        expect(selectionChanges).toBe(1);
    });

    test("a click right after a drag is suppressed exactly once", () => {
        const editor = makeEditor({ nodes: [node("a")] });
        editor.suppressNodeClick = true;
        /** @type {any[]} */
        const clicks = [];
        editor.props.onNodeClick = (/** @type {any} */ payload) =>
            clicks.push(payload.node.id);

        editor.onNodeClick({ node: editor.store.getNode("a"), originalEvent: {} });
        expect(clicks).toEqual([]);
        expect(editor.suppressNodeClick).toBe(false);

        editor.onNodeClick({ node: editor.store.getNode("a"), originalEvent: {} });
        expect(clicks).toEqual(["a"]);
    });

    test("clicking a connection selects it", () => {
        const editor = makeEditor({
            nodes: [
                node("a"),
                node("b", {
                    input: { id: "input", direction: "input", accepts: ["flow"] },
                }),
            ],
            connections: [connection("c1", "a", "b")],
        });

        editor.onConnectionClick({ connectionId: "c1" });

        expect(editor.store.selection.connectionIds).toEqual(["c1"]);
        expect(editor.isConnectionSelected("c1")).toBe(true);
    });
});

describe("FlowEditor: keyboard", () => {
    test("Escape cancels an ongoing node drag and reverts its position", () => {
        const draggedNode = node("a", { position: { x: 10, y: 20 } });
        const editor = makeEditor({ nodes: [draggedNode] });
        /** @type {any[]} */
        const phases = [];
        editor.props.onDrag = (/** @type {any} */ payload) =>
            phases.push(payload.phase);

        editor.onNodePointerDown({
            node: draggedNode,
            originalEvent: pointerEvent({ clientX: 0, clientY: 0 }),
        });
        editor.onPointerMove(pointerEvent({ clientX: 90, clientY: 90 }));
        expect(editor.store.getNode("a").position).not.toEqual({ x: 10, y: 20 });

        editor.onKeyDown({ key: "Escape", preventDefault: () => {} });

        expect(editor.store.getNode("a").position).toEqual({ x: 10, y: 20 });
        expect(editor.store.interaction).toBe(null);
        expect(phases.at(-1)).toBe("cancel");
    });
});

describe("FlowEditor: graph updates", () => {
    test("a new graph that drops the dragged node reports the drag as cancelled", () => {
        const dragged = node("a", { position: { x: 10, y: 20 } });
        const other = node("b");
        const editor = makeEditor({ nodes: [dragged, other] });
        /** @type {any[]} */
        const phases = [];
        editor.props.onDrag = (/** @type {any} */ payload) =>
            phases.push(payload.phase);
        editor.onNodePointerDown({
            node: dragged,
            originalEvent: pointerEvent({ clientX: 0, clientY: 0 }),
        });
        editor.onPointerMove(pointerEvent({ clientX: 30, clientY: 30 }));

        const nextProps = { ...editor.props, nodes: [other] };
        editor.applyProps(nextProps);

        expect(phases).toEqual(["start", "move", "cancel"]);
        expect(editor.store.interaction).toBe(null);
        expect(editor.activePointerId).toBe(null);
    });

    test("a new graph keeps the position of a node the user moved", () => {
        const moved = node("a", { position: { x: 10, y: 20 } });
        const editor = makeEditor({ nodes: [moved, node("b")] });
        editor.onNodePointerDown({
            node: moved,
            originalEvent: pointerEvent({ clientX: 0, clientY: 0 }),
        });
        editor.onPointerMove(pointerEvent({ clientX: 30, clientY: 30 }));
        editor.onPointerUp(pointerEvent({ clientX: 30, clientY: 30 }));

        editor.applyProps({ ...editor.props, nodes: [editor.props.nodes[0]] });

        expect(editor.store.getNode("a")?.position).toEqual({ x: 40, y: 50 });
        expect(editor.store.getNode("b")).toBe(undefined);
    });

    test("turning readonly mid-drag reports the drag as cancelled", () => {
        const dragged = node("a", { position: { x: 10, y: 20 } });
        const editor = makeEditor({ nodes: [dragged] });
        /** @type {any[]} */
        const phases = [];
        editor.props.onDrag = (/** @type {any} */ payload) =>
            phases.push(payload.phase);
        editor.onNodePointerDown({
            node: dragged,
            originalEvent: pointerEvent({ clientX: 0, clientY: 0 }),
        });
        editor.onPointerMove(pointerEvent({ clientX: 30, clientY: 30 }));

        editor.applyProps({ ...editor.props, readonly: true });

        expect(phases).toEqual(["start", "move", "cancel"]);
        expect(editor.store.getNode("a")?.position).toEqual({ x: 10, y: 20 });
        expect(editor.store.readonly).toBe(true);
    });
});

/**
 * @param {string} id
 * @param {{ x: number, y: number }} [position]
 */
function consumerNode(id, position = { x: 0, y: 0 }) {
    return {
        id,
        type: "step",
        position,
        input: { id: "in", direction: "input" },
        outputs: [{ id: "out", direction: "output" }],
    };
}

/**
 * Mounts a FlowEditor the way a consumer does: its graph lives in the
 * consumer's reactive state and is handed down as props.
 *
 * @param {Record<string, any>} [editorProps]
 */
async function mountConsumer(editorProps = {}) {
    /** @type {any} */
    let editor = null;
    patchWithCleanup(FlowEditor.prototype, {
        setup() {
            super.setup();
            editor = this;
        },
    });
    class Consumer extends Component {
        static components = { FlowEditor };
        static template = xml`
            <div style="width: 800px; height: 600px">
                <FlowEditor nodes="this.state.nodes"
                            connections="this.state.connections"
                            viewport="this.viewport"
                            readonly="this.state.readonly"
                            onConnect.bind="this.onConnect"
                            onConnectionRejected.bind="this.onConnectionRejected"
                            onDrag.bind="this.onDrag"/>
            </div>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            this.state = proxy({
                nodes: [
                    consumerNode("a"),
                    consumerNode("b"),
                    consumerNode("c", { x: 400, y: 0 }),
                ],
                connections: [],
                readonly: false,
            });
            this.viewport = { x: 0, y: 0, scale: 1 };
        }
        /** @param {any} params */
        onDrag(params) {
            editorProps.onDrag?.(params);
        }
        /** @param {any} candidate */
        onConnect(candidate) {
            return editorProps.onConnect ? editorProps.onConnect(candidate) : candidate;
        }
        /** @param {any} params */
        onConnectionRejected(params) {
            editorProps.onConnectionRejected?.(params);
        }
    }
    const consumer = await mountWithCleanup(Consumer);
    return { consumer, editor };
}

describe("FlowEditor: mounted in a consumer", () => {
    for (const [what, change] of /** @type {const} */ ([
        [
            "drops the dragged node",
            (/** @type {any} */ consumer) => {
                consumer.state.nodes = consumer.state.nodes.filter(
                    (/** @type {any} */ drawn) => drawn.id !== "a",
                );
            },
        ],
        [
            "turns readonly",
            (/** @type {any} */ consumer) => {
                consumer.state.readonly = true;
            },
        ],
    ])) {
        test(`a consumer that ${what} mid-drag hears the drag cancelled`, async () => {
            /** @type {string[]} */
            const phases = [];
            const { consumer, editor } = await mountConsumer({
                onDrag: (/** @type {any} */ { phase }) => phases.push(phase),
            });
            editor.onNodePointerDown({
                node: editor.store.getNode("a"),
                originalEvent: pointerEvent({ clientX: 0, clientY: 0 }),
            });
            editor.onPointerMove(pointerEvent({ clientX: 30, clientY: 30 }));

            change(consumer);
            await animationFrame();

            expect(phases).toEqual(["start", "move", "cancel"]);
            expect(editor.store.interaction).toBe(null);
            expect(editor.activePointerId).toBe(null);
        });
    }

    test("a consumer that drops one node keeps the others where the user moved them", async () => {
        const { consumer, editor } = await mountConsumer();
        editor.store.moveNode("a", { x: 40, y: 60 });
        await animationFrame();

        consumer.state.nodes = consumer.state.nodes.filter(
            (/** @type {any} */ drawn) => drawn.id !== "b",
        );
        await animationFrame();

        expect(".o_flow_editor_node").toHaveCount(2);
        expect(editor.store.getNode("b")).toBe(undefined);
        expect(editor.store.getNode("a").position).toEqual({ x: 40, y: 60 });
        expect(editor.store.getNode("c").position).toEqual({ x: 400, y: 0 });
    });

    test("a consumer that reloads its graph with new objects gets its own positions back", async () => {
        const { consumer, editor } = await mountConsumer();
        editor.store.moveNode("a", { x: 40, y: 60 });
        await animationFrame();

        consumer.state.nodes = consumer.state.nodes.map((/** @type {any} */ drawn) => ({
            ...toRaw(drawn),
            position: { x: 200, y: 200 },
        }));
        await animationFrame();

        expect(editor.store.getNode("a").position).toEqual({ x: 200, y: 200 });
        expect(editor.store.getNode("c").position).toEqual({ x: 200, y: 200 });
    });

    test("a consumer whose graph already carries the connection it persists does not see it rejected", async () => {
        /** @type {string[]} */
        const rejections = [];
        const persisted = new Deferred();
        /** @type {any} */
        let consumer = null;
        const mounted = await mountConsumer({
            onConnect: async (/** @type {any} */ candidate) => {
                consumer.state.connections = [...consumer.state.connections, candidate];
                await persisted;
                return candidate;
            },
            onConnectionRejected: (/** @type {any} */ { validation }) =>
                rejections.push(validation.reason),
        });
        consumer = mounted.consumer;
        const editor = mounted.editor;

        const connecting = editor.connectPorts(
            { sourceNodeId: "a", sourcePortId: "out" },
            { node: editor.store.getNode("b"), portId: "in" },
        );
        await animationFrame();
        persisted.resolve();
        await connecting;
        await animationFrame();

        expect(rejections).toEqual([]);
        expect(editor.store.connections).toHaveLength(1);
    });

    test("a consumer that draws the candidate and persists it under a new id does not see it rejected", async () => {
        /** @type {string[]} */
        const rejections = [];
        const persisted = new Deferred();
        /** @type {any} */
        let consumer = null;
        const mounted = await mountConsumer({
            onConnect: async (/** @type {any} */ candidate) => {
                consumer.state.connections = [...consumer.state.connections, candidate];
                await persisted;
                return { ...candidate, id: 42 };
            },
            onConnectionRejected: (/** @type {any} */ { validation }) =>
                rejections.push(validation.reason),
        });
        consumer = mounted.consumer;
        const editor = mounted.editor;

        const connecting = editor.connectPorts(
            { sourceNodeId: "a", sourcePortId: "out" },
            { node: editor.store.getNode("b"), portId: "in" },
        );
        await animationFrame();
        persisted.resolve();
        await connecting;
        await animationFrame();

        expect(rejections).toEqual([]);
        expect(editor.store.connections).toHaveLength(1);
    });

    test("a connection only the editor draws is kept across a consumer graph update", async () => {
        const { consumer, editor } = await mountConsumer({
            onConnect: (/** @type {any} */ candidate) => ({ ...candidate, id: 7 }),
        });
        await editor.connectPorts(
            { sourceNodeId: "a", sourcePortId: "out" },
            { node: editor.store.getNode("b"), portId: "in" },
        );
        expect(editor.store.connections.map((/** @type {any} */ c) => c.id)).toEqual([
            7,
        ]);

        consumer.state.nodes = consumer.state.nodes.filter(
            (/** @type {any} */ drawn) => drawn.id !== "c",
        );
        await animationFrame();
        expect(editor.store.connections.map((/** @type {any} */ c) => c.id)).toEqual([
            7,
        ]);
        expect(".o_flow_editor_node").toHaveCount(2);

        consumer.state.nodes = consumer.state.nodes.filter(
            (/** @type {any} */ drawn) => drawn.id !== "b",
        );
        await animationFrame();
        expect(editor.store.connections).toEqual([]);
    });
});
