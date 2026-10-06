/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { compareDates, toDateTime } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";

import { connectablePillPairs, shouldConnectPills } from "./gantt_connectors.js";
import { useGanttConnectorDraggable } from "./gantt_helpers.js";
import { GanttRendererCore, rtl } from "./gantt_renderer_core.js";

const NEW_CONNECTOR_ID = "__connector__new";

export class GanttRendererConnectors extends GanttRendererCore {
    setup() {
        super.setup();
        this.ui = useService("ui");
        /** @type {Record<ConnectorId, ConnectorProps>} */
        this.connectors = proxy({});
        this.removeConnectorHandler = (connectorId) =>
            this.onRemoveButtonClick(connectorId);
        this.connectorHoverHandler = () => this.onConnectorHover();
        /** @type {ConnectorId | null} */
        this.highlightedConnectorId = null;
        let initialPillId;
        this.connectorDragState = useGanttConnectorDraggable({
            ref: this.gridRef,
            elements: ".o_connector_creator_bullet",
            parentWrapper: ".o_gantt_cells .o_gantt_pill_wrapper",
            onWillStartDrag: this.cleanMultiSelection.bind(this),
            onDragStart: ({ sourcePill, x, y, addClass }) => {
                this.popover.close();
                initialPillId = sourcePill.dataset.pillId;
                addClass(sourcePill, "o_connector_creator_lock");
                this.setConnector({
                    id: NEW_CONNECTOR_ID,
                    highlighted: true,
                    sourcePoint: { left: x, top: y },
                    targetPoint: { left: x, top: y },
                });
                this.setStickyPill(sourcePill);
                this.interaction.mode = "connect";
            },
            onDrag: ({ connectorCenter, x, y }) => {
                this.setConnector({
                    id: NEW_CONNECTOR_ID,
                    sourcePoint: { left: connectorCenter.x, top: connectorCenter.y },
                    targetPoint: { left: x, top: y },
                });
            },
            onDragEnd: () => {
                this.setConnector({
                    id: NEW_CONNECTOR_ID,
                    sourcePoint: null,
                    targetPoint: null,
                });
                this.setStickyPill();
                this.interaction.mode = null;
            },
            onDrop: ({ target }) => {
                if (initialPillId === target.dataset.pillId) {
                    return;
                }
                const { id: masterId } = this.pills[initialPillId].record;
                const { id: slaveId } = this.pills[target.dataset.pillId].record;
                this.model.createDependency(masterId, slaveId);
            },
        });
    }

    computeVisibleConnectors() {
        const visibleConnectorIds = new Set([NEW_CONNECTOR_ID]);

        for (const pill of this.pillsToRender) {
            const row = this.getRowFromPill(pill);
            if (row.isGroup) {
                continue;
            }
            for (const connectorId of this.mappingPillToConnectors[pill.id] || []) {
                visibleConnectorIds.add(connectorId);
            }
        }

        this.connectorsToRender = [];
        for (const connectorId in this.connectors) {
            if (!visibleConnectorIds.has(connectorId)) {
                continue;
            }
            this.connectorsToRender.push(this.connectors[connectorId]);
            const { sourcePillId, targetPillId } =
                this.mappingConnectorToPills[connectorId];
            if (sourcePillId) {
                this.addToPillsToRender(this.pills[sourcePillId]);
            }
            if (targetPillId) {
                this.addToPillsToRender(this.pills[targetPillId]);
            }
        }
    }

    /**
     * @param {ConnectorId} connectorId
     */
    deleteConnector(connectorId) {
        delete this.connectors[connectorId];
        delete this.mappingConnectorToPills[connectorId];
    }

    /**
     * @param {number} masterId
     * @param {string} masterRowId
     * @param {number} slaveId
     * @param {string} slaveRowId
     */
    shouldConnectPills(masterId, masterRowId, slaveId, slaveRowId) {
        return shouldConnectPills(
            this.mappingRecordToPillsByRow,
            this.mappingRowToPillsByRecord,
            masterId,
            masterRowId,
            slaveId,
            slaveRowId,
        );
    }

    generateConnectors() {
        this.nextConnectorId = 1;
        this.setConnector({
            id: NEW_CONNECTOR_ID,
            highlighted: true,
            sourcePoint: null,
            targetPoint: null,
        });
        for (const [sourcePill, targetPill] of connectablePillPairs(
            this.mappingRecordToPillsByRow,
            this.mappingRowToPillsByRecord,
        )) {
            this.setConnector(...this.getConnectorParams(sourcePill, targetPill));
        }
    }

    /**
     * @param {Pill} sourcePill
     * @param {Pill} targetPill
     */
    getConnectorParams(sourcePill, targetPill) {
        return [
            { alert: this.getConnectorAlert(sourcePill.record, targetPill.record) },
            sourcePill.id,
            targetPill.id,
            this.shouldConnectorBeDashed(sourcePill),
        ];
    }

    shouldConnectorBeDashed(sourcePill) {
        return false;
    }

    /**
     *
     * @param {Object} masterRecord
     * @param {Object} slaveRecord
     * @returns {import("./gantt_connector").ConnectorAlert | null}
     */
    getConnectorAlert(masterRecord, slaveRecord) {
        const { dateStartField, dateStopField } = this.model.metaData;
        const slaveStart = toDateTime(slaveRecord[dateStartField]);
        if (compareDates(slaveStart, toDateTime(masterRecord[dateStopField])) < 0) {
            if (
                compareDates(slaveStart, toDateTime(masterRecord[dateStartField])) < 0
            ) {
                return "error";
            } else {
                return "warning";
            }
        }
        return null;
    }

    /**
     * @param {"top"|"bottom"} vertical the vertical alignment of the connector creator
     * @returns {{ vertical: "top"|"bottom", horizontal: "left"|"right" }}
     */
    getConnectorCreatorAlignment(vertical) {
        const alignment = { vertical };
        if (rtl()) {
            alignment.horizontal = vertical === "top" ? "right" : "left";
        } else {
            alignment.horizontal = vertical === "top" ? "left" : "right";
        }
        return alignment;
    }

    /**
     * @param {PillId} pillId
     * @param {boolean} onRight
     */
    getPoint(pillId, onRight) {
        if (rtl()) {
            onRight = !onRight;
        }
        const pillEl = this.getPillEl(pillId);
        const pillRect = pillEl.getBoundingClientRect();
        return {
            left: pillRect.left + (onRight ? pillRect.width : 0),
            top: pillRect.top + pillRect.height / 2,
        };
    }

    highlightPill(pillId, highlighted) {
        const pill = this.pills[pillId];
        if (!pill) {
            return;
        }
        const pillWrapper = this.getPillWrapperEl(pillId);
        if (pillWrapper) {
            pillWrapper.classList.toggle("highlight", highlighted);
            pillWrapper.classList.toggle(
                "o_connector_creator_highlight",
                highlighted && this.connectorDragState.dragging,
            );
        }
    }

    indexPillsForConnectors() {
        const { dependencyField } = this.model.metaData;
        /** @type {Record<number, { masterIds: number[], pills: Record<RowId, Pill> }>} */
        this.mappingRecordToPillsByRow = {};
        /** @type {Record<RowId, Record<number, Pill>>} */
        this.mappingRowToPillsByRecord = {};
        /** @type {Record<ConnectorId, { sourcePillId: PillId, targetPillId: PillId }>} */
        this.mappingConnectorToPills = {};
        /** @type {Record<PillId, ConnectorId>} */
        this.mappingPillToConnectors = {};
        for (const pill of Object.values(this.pills)) {
            const { record, rowId } = pill;
            if (
                this.rowByIds[rowId].isGroup ||
                !this.shouldRenderRecordConnectors(record)
            ) {
                continue;
            }
            this.mappingRecordToPillsByRow[record.id] ??= {
                masterIds: record[dependencyField],
                pills: {},
            };
            this.mappingRecordToPillsByRow[record.id].pills[rowId] = pill;
            this.mappingRowToPillsByRecord[rowId] ??= {};
            this.mappingRowToPillsByRecord[rowId][record.id] = pill;
        }
    }

    initializeConnectors() {
        for (const connectorId in this.connectors) {
            this.deleteConnector(connectorId);
        }
    }

    /**
     * @param {Partial<ConnectorProps>} params
     * @param {PillId | null} [sourceId=null]
     * @param {PillId | null} [targetId=null]
     */
    setConnector(params, sourceId = null, targetId = null, dashed = null) {
        const connectorParams = { ...params };
        const connectorId = params.id || `__connector__${this.nextConnectorId++}`;

        if (sourceId) {
            connectorParams.sourcePoint = () => this.getPoint(sourceId, true);
        }

        if (targetId) {
            connectorParams.targetPoint = () => this.getPoint(targetId, false);
        }

        if (dashed) {
            connectorParams.dashed = true;
        }

        if (this.connectors[connectorId]) {
            Object.assign(this.connectors[connectorId], connectorParams);
        } else {
            this.connectors[connectorId] = {
                id: connectorId,
                highlighted: false,
                displayButtons: false,
                ...connectorParams,
            };
            this.mappingConnectorToPills[connectorId] = {
                sourcePillId: sourceId,
                targetPillId: targetId,
            };
        }

        if (sourceId) {
            if (!this.mappingPillToConnectors[sourceId]) {
                this.mappingPillToConnectors[sourceId] = [];
            }
            this.mappingPillToConnectors[sourceId].push(connectorId);
        }

        if (targetId) {
            if (!this.mappingPillToConnectors[targetId]) {
                this.mappingPillToConnectors[targetId] = [];
            }
            this.mappingPillToConnectors[targetId].push(connectorId);
        }
    }

    /**
     * @return {boolean}
     */
    shouldRenderConnectors() {
        return Boolean(
            this.model.metaData.dependencyField &&
            !this.model.useSampleModel &&
            !this.ui.isSmall,
        );
    }

    /**
     * @param {RelationalRecord} record
     * @return {boolean}
     */
    shouldRenderRecordConnectors(record) {
        return this.shouldRenderConnectors();
    }

    onConnectorHover() {
        return false;
    }

    /**
     * @param {ConnectorId | null} connectorId
     * @param {boolean} highlighted
     */
    toggleConnectorHighlighting(connectorId, highlighted) {
        const connector = this.connectors[connectorId];
        if (!connector || (!connector.highlighted && !highlighted)) {
            return;
        }

        connector.highlighted = highlighted;
        connector.displayButtons = highlighted;
        if (highlighted) {
            this.highlightedConnectorId = connectorId;
        } else if (this.highlightedConnectorId === connectorId) {
            this.highlightedConnectorId = null;
        }

        if (this.onConnectorHover()) {
            const { sourcePillId, targetPillId } =
                this.mappingConnectorToPills[connectorId];

            this.highlightPill(sourcePillId, highlighted);
            this.highlightPill(targetPillId, highlighted);
        }
    }

    getRecordIds(connectorId) {
        const { sourcePillId, targetPillId } =
            this.mappingConnectorToPills[connectorId];
        return {
            masterId: this.pills[sourcePillId]?.record.id,
            slaveId: this.pills[targetPillId]?.record.id,
        };
    }

    /**
     *
     * @param {ConnectorId} connectorId
     */
    onRemoveButtonClick(connectorId) {
        const { masterId, slaveId } = this.getRecordIds(connectorId);
        this.model.removeDependency(masterId, slaveId);
    }
}
