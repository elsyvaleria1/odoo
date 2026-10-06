// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { proxy } from "@odoo/owl";
import { FlowEditorStore } from "@web/core/flow_editor/flow_editor_store";

describe.current.tags("headless");

/**
 * @param {import("@web/core/flow_editor/flow_types").FlowNodeId} id
 * @param {import("@web/core/flow_editor/flow_types").FlowPosition} [position]
 * @returns {import("@web/core/flow_editor/flow_types").FlowNode}
 */
function node(id, position = { x: 0, y: 0 }) {
    return {
        id,
        type: "test",
        position,
        input: {
            id: "input",
            direction: "input",
            accepts: ["flow"],
        },
        outputs: [
            {
                id: "output",
                direction: "output",
                provides: "flow",
            },
        ],
    };
}

/**
 * @param {import("@web/core/flow_editor/flow_types").FlowConnectionId} id
 * @param {import("@web/core/flow_editor/flow_types").FlowNodeId} sourceNodeId
 * @param {import("@web/core/flow_editor/flow_types").FlowNodeId} targetNodeId
 * @returns {import("@web/core/flow_editor/flow_types").FlowConnection}
 */
function connection(id, sourceNodeId, targetNodeId) {
    return {
        id,
        sourceNodeId,
        sourcePortId: "output",
        targetNodeId,
        targetPortId: "input",
    };
}

describe("FlowEditorStore", () => {
    test("adds and removes nodes together with their connections", () => {
        const store = new FlowEditorStore();
        expect(store.addNode(node("first"))).toBe(true);
        expect(store.addNode(node("second"))).toBe(true);
        expect(store.addNode(node("first"))).toBe(false);
        expect(store.addConnection(connection("connection", "first", "second"))).toBe(
            true,
        );

        expect(store.removeNode("first")).toBe(true);
        expect(store.nodes.map(({ id }) => id)).toEqual(["second"]);
        expect(store.connections).toEqual([]);
    });

    test("adds and removes connections without accepting duplicate ids", () => {
        const graphConnection = connection("connection", "first", "second");
        const store = new FlowEditorStore({
            nodes: [node("first"), node("second")],
        });

        expect(store.addConnection(graphConnection)).toBe(true);
        expect(store.addConnection(graphConnection)).toBe(false);
        expect(store.removeConnection("connection")).toBe(true);
        expect(store.removeConnection("connection")).toBe(false);
    });

    test("keeps only existing unique items in a multiple selection", () => {
        const store = new FlowEditorStore({
            nodes: [node("first"), node("second")],
            connections: [connection("connection", "first", "second")],
        });

        store.setSelection({
            nodeIds: ["first", "missing", "first", "second"],
            connectionIds: ["missing", "connection", "connection"],
        });

        expect(store.selection).toEqual({
            nodeIds: ["first", "second"],
            connectionIds: ["connection"],
        });
    });

    test("cancels a node drag by restoring its original position", () => {
        const origin = { x: 10, y: 20 };
        const store = new FlowEditorStore({ nodes: [node("first", origin)] });
        expect(
            store.startInteraction({
                type: "node_drag",
                nodeId: "first",
                origin,
            }),
        ).toBe(true);
        store.moveNode("first", { x: 100, y: 200 });

        store.cancelInteraction();

        expect(store.getNode("first")?.position).toEqual(origin);
        expect(store.interaction).toBe(null);
    });

    test("a new graph keeps what the user did to the items its consumer handed back", () => {
        const moved = node("moved", { x: 0, y: 0 });
        const reset = node("reset", { x: 0, y: 0 });
        const dropped = node("dropped");
        const kept = connection("kept", "moved", "reset");
        const removedHere = connection("removed-here", "reset", "moved");
        const previous = proxy({
            nodes: [moved, reset, dropped],
            connections: [kept, removedHere],
        });
        const store = new FlowEditorStore(previous);
        store.moveNode("moved", { x: 40, y: 50 });
        store.moveNode("reset", { x: 40, y: 50 });
        store.removeConnection("removed-here");
        store.addConnection(connection("made-here", "moved", "reset"));
        store.addConnection(connection("made-on-dropped", "moved", "dropped"));
        store.setSelection({ nodeIds: ["dropped"], connectionIds: ["kept"] });

        const next = proxy({
            nodes: [
                previous.nodes[0],
                { ...previous.nodes[1], position: { x: 300, y: 300 } },
            ],
            connections: [...previous.connections],
        });
        expect(store.setGraph(next, previous)).toBe(null);

        expect(store.getNode("moved")?.position).toEqual({ x: 40, y: 50 });
        expect(store.getNode("reset")?.position).toEqual({ x: 300, y: 300 });
        expect(store.getNode("dropped")).toBe(undefined);
        expect(store.connections.map(({ id }) => id)).toEqual(["kept", "made-here"]);
        expect(store.getConnection("made-here")?.targetNodeId).toBe("reset");
        expect(store.selection).toEqual({ nodeIds: [], connectionIds: ["kept"] });
    });

    test("a new graph ends only the interactions it makes impossible", () => {
        const graph = { nodes: [node("first"), node("second")], connections: [] };
        const store = new FlowEditorStore(graph);

        store.startInteraction({ type: "pan" });
        expect(store.setGraph({ ...graph, nodes: [...graph.nodes] }, graph)).toBe(null);
        expect(store.interaction).toEqual({ type: "pan" });
        store.endInteraction();

        store.startInteraction({
            type: "node_drag",
            nodeId: "second",
            origin: { x: 0, y: 0 },
        });
        const withoutFirst = { ...graph, nodes: [graph.nodes[1]] };
        expect(store.setGraph(withoutFirst, graph)).toBe(null);
        expect(store.interaction?.type).toBe("node_drag");

        const ended = store.setGraph({ ...graph, nodes: [] }, withoutFirst);
        expect(ended?.type).toBe("node_drag");
        expect(store.interaction).toBe(null);
    });

    test("looks nodes and connections up by id without scanning them", () => {
        const store = new FlowEditorStore({
            nodes: [node("first"), node("second")],
            connections: [connection("connection", "first", "second")],
        });
        store.nodes.find = store.connections.find = () => {
            throw new Error("scanned");
        };

        expect(store.getNode("second")?.id).toBe("second");
        expect(store.getConnection("connection")?.sourceNodeId).toBe("first");
        expect(store.getNextConnectionId()).toBe("flow-connection-1");
    });
});
