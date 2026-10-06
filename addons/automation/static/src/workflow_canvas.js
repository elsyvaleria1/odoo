/** @odoo-module native */

import {
    Component,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { FlowEditor } from "@web/core/flow_editor/flow_editor";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

import {
    canConnect,
    edgeLabel,
    layoutWorkflow,
    linkClasses,
    toFlowGraph,
} from "./workflow_graph.js";
import { WorkflowNode } from "./workflow_node.js";

const CHANNEL_PREFIX = "automation.workflow/";
const UPDATE_TYPE = "automation.workflow/update";

export class WorkflowCanvas extends Component {
    static template = "automation.WorkflowCanvas";
    static components = { FlowEditor };
    static props = {
        record: t.object(),
        readonly: t.boolean().optional(),
        mode: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    NodeComponent = WorkflowNode;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.bus = useService("bus_service");
        this.state = proxy({
            status: "idle",
            error: "",
            countNode: 0,
            countEdge: 0,
            selectedEdgeId: null,
            runs: [],
            runtimeId: null,
            runtimeState: null,
            nodes: [],
            connections: [],
        });
        // null asks the server to choose (a live run, else the definition);
        // false pins the definition; an id pins that run.
        this.requestedRuntimeId = null;
        this.payload = null;
        this.listening = null;
        // Handed to the editor as a prop, so it is replaced only by a load: a
        // fresh object on every pan frame would reset the editor's own viewport
        // mid-gesture.
        this.viewport = null;
        this.pendingViewport = null;
        // Panning and wheel-zooming both report continuously; the reader's
        // resting position is what is worth a row, not every frame of getting
        // there. execBeforeUnmount flushes the last one if they navigate away.
        this.saveViewport = useDebounced(() => this.persistViewport(), 400, {
            execBeforeUnmount: true,
        });
        this.onWorkflowUpdate = ({ automation_id, runtime_id }) => {
            if (automation_id !== this.ruleId) {
                return;
            }
            if (this.isRunMode) {
                if (runtime_id === this.resId) {
                    this.load();
                }
                return;
            }
            // Follow the run that just moved, unless the reader has pinned a
            // different one -- their choice outranks the notification.
            if (this.requestedRuntimeId === null && runtime_id) {
                this.requestedRuntimeId = runtime_id;
            }
            this.load();
        };
        onWillStart(async () => {
            await this.load();
            this.listen();
        });
        this.loadedVersion = this.versionOf(this.props.record);
        onWillUpdateProps(async (nextProps) => {
            const version = this.versionOf(nextProps.record);
            if (nextProps.record.resId !== this.resId) {
                this.stopListening();
                this.loadedVersion = version;
                await this.load(nextProps.record.resId);
                this.listen(this.ruleIdOf(nextProps.record));
            } else if (this.isRunMode && version !== this.loadedVersion) {
                // A run's form reloads its record after every button; the
                // steps moved with it, and the bus may not be there to say so.
                this.loadedVersion = version;
                await this.load(nextProps.record.resId);
            }
        });
        onWillUnmount(() => this.stopListening());
    }

    get isRunMode() {
        return this.props.mode === "run";
    }

    get resId() {
        return this.props.record.resId;
    }

    get ruleId() {
        return this.ruleIdOf(this.props.record);
    }

    ruleIdOf(record) {
        return this.isRunMode ? record.data.automation_id?.id || false : record.resId;
    }

    versionOf(record) {
        return this.isRunMode ? `${record.data.state}/${record.data.write_date}` : "";
    }

    get isEditable() {
        return !this.isRunMode && !this.props.readonly && !this.props.record.isNew;
    }

    get edges() {
        return this.payload?.edges || [];
    }

    async load(resId = this.resId) {
        if (!resId) {
            this.state.status = "unsaved";
            return;
        }
        this.state.status = "loading";
        let payload;
        try {
            payload = this.isRunMode
                ? await this.orm.call("automation.runtime", "get_workflow_graph", [
                      [resId],
                  ])
                : await this.orm.call(
                      "automation.rule",
                      "get_workflow_graph",
                      [[resId]],
                      {
                          runtime_id: this.requestedRuntimeId,
                      },
                  );
        } catch (error) {
            this.state.status = "error";
            this.state.error = error.message || String(error);
            return;
        }
        this.payload = payload;
        const graph = toFlowGraph(payload);
        this.state.nodes = graph.nodes;
        this.state.connections = graph.connections;
        this.state.countNode = payload.nodes.length;
        this.state.countEdge = payload.edges.length;
        this.state.runs = payload.runs || [];
        this.state.runtimeId = payload.runtime_id;
        this.state.runtimeState = payload.runtime_state;
        this.state.selectedEdgeId = null;
        this.viewport = payload.viewport;
        this.pendingViewport = null;
        this.state.status = payload.nodes.length ? "ready" : "empty";
        // A graph nobody has placed is laid out here rather than server-side,
        // and banking it is what keeps the reader's own arrangement from being
        // recomputed on the next read.
        if (!payload.is_positioned && this.isEditable && this.state.nodes.length) {
            await this.persistPositions(this.state.nodes);
        }
    }

    async persistPositions(nodes) {
        await Promise.all(
            nodes.map((node) =>
                this.orm.write("ir.actions.server", [node.id], {
                    pos_x: Math.round(node.position.x),
                    pos_y: Math.round(node.position.y),
                }),
            ),
        );
    }

    listen(ruleId = this.ruleId) {
        if (!ruleId || this.listening) {
            return;
        }
        this.listening = `${CHANNEL_PREFIX}${ruleId}`;
        this.bus.addChannel(this.listening);
        this.bus.subscribe(UPDATE_TYPE, this.onWorkflowUpdate);
    }

    stopListening() {
        if (!this.listening) {
            return;
        }
        this.bus.unsubscribe(UPDATE_TYPE, this.onWorkflowUpdate);
        this.bus.deleteChannel(this.listening);
        this.listening = null;
    }

    get minNodeSize() {
        return this.payload.node_size.min;
    }

    get maxNodeSize() {
        return this.payload.node_size.max;
    }

    onViewportChange(viewport) {
        this.pendingViewport = viewport;
        this.saveViewport();
    }

    async persistViewport() {
        const viewport = this.pendingViewport;
        if (!viewport || !this.ruleId) {
            return;
        }
        try {
            await this.orm.call("automation.rule", "set_workflow_viewport", [
                [this.ruleId],
                viewport.x,
                viewport.y,
                viewport.scale,
            ]);
        } catch {
            // Losing a viewport costs the reader one pan, so it is not worth a
            // dialog; the graph itself is unaffected.
        }
    }

    async onResize({ phase, node, size }) {
        if (phase !== "end" || !this.isEditable || !node) {
            return;
        }
        await this.orm.write("ir.actions.server", [node.id], {
            pos_width: Math.round(size.width),
            pos_height: Math.round(size.height),
        });
    }

    getConnectionClass(connection) {
        return linkClasses(connection.data || {});
    }

    getConnectionLabel(connection) {
        return edgeLabel(connection.data || {});
    }

    /**
     * The editor's own rules already refuse a self-connection and a repeat of
     * the same two ports; this adds the one the model enforces on top of them,
     * `workflow.edge._edge_uniq`, which is per PAIR of steps whatever
     * condition each connection carries.
     */
    canConnect(connection) {
        return canConnect(this.edges, connection.sourceNodeId, connection.targetNodeId);
    }

    async onConnect(connection) {
        try {
            const [edgeId] = await this.orm.create("workflow.edge", [
                {
                    source_node_id: connection.sourceNodeId,
                    target_node_id: connection.targetNodeId,
                    condition: connection.sourcePortId,
                },
            ]);
            this.edges.push({
                id: edgeId,
                source: connection.sourceNodeId,
                target: connection.targetNodeId,
                condition: connection.sourcePortId,
            });
            this.state.countEdge++;
            return { ...connection, id: edgeId, data: this.edges.at(-1) };
        } catch (error) {
            this.notify(error, _t("That connection was refused"));
            return false;
        }
    }

    async onDisconnect({ connection }) {
        try {
            await this.orm.unlink("workflow.edge", [connection.id]);
        } catch (error) {
            this.notify(error, _t("That connection could not be removed"));
            return false;
        }
        this.payload.edges = this.edges.filter((edge) => edge.id !== connection.id);
        this.state.countEdge = this.edges.length;
        return true;
    }

    async onNodeDelete({ node }) {
        try {
            await this.orm.unlink("ir.actions.server", [node.id]);
        } catch (error) {
            this.notify(error, _t("That step could not be removed"));
            return false;
        }
        this.payload.nodes = this.payload.nodes.filter((step) => step.id !== node.id);
        this.payload.edges = this.edges.filter(
            (edge) => edge.source !== node.id && edge.target !== node.id,
        );
        this.state.nodes = this.state.nodes.filter((drawn) => drawn.id !== node.id);
        this.state.connections = this.state.connections.filter(
            (drawn) => drawn.sourceNodeId !== node.id && drawn.targetNodeId !== node.id,
        );
        this.state.countNode = this.payload.nodes.length;
        this.state.countEdge = this.edges.length;
        if (
            !this.state.connections.some(
                (drawn) => drawn.id === this.state.selectedEdgeId,
            )
        ) {
            this.state.selectedEdgeId = null;
        }
        if (!this.state.countNode) {
            this.state.status = "empty";
        }
        return true;
    }

    async onDrag({ phase, node, position }) {
        if (phase !== "end" || !this.isEditable || !node) {
            return;
        }
        await this.orm.write("ir.actions.server", [node.id], {
            pos_x: Math.round(position.x),
            pos_y: Math.round(position.y),
        });
    }

    onNodeClick({ node, originalEvent }) {
        if (originalEvent.detail < 2) {
            return;
        }
        if (this.isRunMode) {
            this.openStep(node.data?.line_id, node.data?.name);
        } else {
            this.openAction(node.id, node.data?.name);
        }
    }

    onSelectionChange({ connectionIds }) {
        this.state.selectedEdgeId = connectionIds[0] ?? null;
    }

    onConnectionRejected({ validation }) {
        if (
            validation.reason === "duplicate" ||
            validation.reason === "consumer_rejected"
        ) {
            this.notification.add(_t("These two steps are already connected."), {
                type: "warning",
            });
        }
    }

    async removeSelectedEdge() {
        const connection = this.state.connections.find(
            (candidate) => candidate.id === this.state.selectedEdgeId,
        );
        if (!connection || !(await this.onDisconnect({ connection }))) {
            return;
        }
        await this.load();
    }

    async relayout() {
        const positions = layoutWorkflow(
            this.payload.nodes,
            this.edges,
            this.payload.node_size.default,
        );
        this.state.nodes = this.state.nodes.map((node) => ({
            ...node,
            position: positions.get(node.id) || node.position,
        }));
        if (this.isEditable) {
            await this.persistPositions(this.state.nodes);
        }
    }

    async selectRun(value) {
        this.requestedRuntimeId = value === "definition" ? false : Number(value);
        await this.load();
    }

    get runLabel() {
        const run = this.state.runs.find(
            (candidate) => candidate.id === this.state.runtimeId,
        );
        return run ? `${run.name} — ${run.progress}` : "";
    }

    notify(error, title) {
        this.notification.add(error.data?.message || error.message, {
            type: "danger",
            title,
        });
    }

    openAction(nodeId, name) {
        if (!nodeId) {
            return;
        }
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: name || _t("Step"),
                res_model: "ir.actions.server",
                res_id: nodeId,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.load() },
        );
    }

    openStep(lineId, name) {
        if (!lineId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || _t("Step"),
            res_model: "automation.runtime.line",
            res_id: lineId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    addStep() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("New Step"),
                res_model: "ir.actions.server",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_automation_rule_id: this.resId,
                    default_model_id: this.props.record.data.model_id?.id,
                    default_usage: "automation",
                    is_modal: 1,
                },
            },
            { onClose: () => this.load() },
        );
    }
}

registry.category("view_widgets").add("automation_workflow_canvas", {
    component: WorkflowCanvas,
    extractProps: ({ attrs }) => ({
        mode: attrs.mode === "run" ? "run" : "definition",
    }),
    // A run's canvas redraws when its record was written, whether or not the
    // form shows when that was.
    fieldDependencies: ({ attrs }) =>
        attrs.mode === "run" ? [{ name: "write_date", type: "datetime" }] : [],
});
