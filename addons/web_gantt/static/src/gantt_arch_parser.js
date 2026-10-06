/** @odoo-module native */
import { evaluateExpr } from "@web/core/py_js/py";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { irToElement, literalNbsp } from "@web/views/ir/view_ir";
import { ViewArchParser, visitIR } from "@web/views/view_arch_parser";
import { getActiveActions } from "@web/views/view_utils";

import { PARTS, RANGES, SCALES } from "./gantt_ranges.js";

const DECORATIONS = [
    "decoration-danger",
    "decoration-info",
    "decoration-secondary",
    "decoration-success",
    "decoration-warning",
];
const RESCHEDULE_METHODS = {
    manual: _t("Manual Reschedule"),
    consumeBuffer: _t("Auto-Reschedule (Use Buffer)"),
    maintainBuffer: _t("Auto-Reschedule (Keep Buffer)"),
};

export class GanttArchParser extends ViewArchParser {
    /** @type {"element" | "ir"} */
    static consumes = "ir";

    /**
     * @param {import("@web/views/ir/view_ir_schema").ViewIRNode | Element | string} arch
     */
    parse(arch) {
        let infoFromRootNode;
        const decorationFields = [];
        const popoverArchParams = {
            displayGenericButtons: true,
            bodyTemplate: null,
            footerTemplate: null,
        };

        visitIR(this.toIR(arch), (node) => {
            switch (node.kind) {
                case "gantt": {
                    infoFromRootNode = getInfoFromRootNode(node);
                    break;
                }
                case "field": {
                    const fieldName = node.attrs?.name;
                    decorationFields.push(fieldName);
                    break;
                }
                case "templates": {
                    // the popover body and footer are templates the renderer
                    // compiles: the <templates> sub-tree is materialised once
                    const templates = irToElement(node, { text: literalNbsp });
                    const body =
                        templates.querySelector("[t-name=gantt-popover]") || null;
                    if (body) {
                        popoverArchParams.bodyTemplate = body.cloneNode(true);
                        popoverArchParams.bodyTemplate.removeAttribute("t-name");
                        const footer =
                            popoverArchParams.bodyTemplate.querySelector("footer");
                        if (footer) {
                            popoverArchParams.displayGenericButtons = false;
                            footer.remove();
                            const footerTemplate = new Document().createElement("t");
                            footerTemplate.append(...footer.children);
                            popoverArchParams.footerTemplate = footerTemplate;
                            const replace = footer.getAttribute("replace");
                            if (replace && !exprToBoolean(replace)) {
                                popoverArchParams.displayGenericButtons = true;
                            }
                        }
                        let hasRemainingChild = false;
                        for (const child of popoverArchParams.bodyTemplate.childNodes) {
                            if (child.nodeType === 8) {
                                continue;
                            }
                            if (child.nodeType === 3 && !child.data.trim()) {
                                continue;
                            }
                            hasRemainingChild = true;
                            break;
                        }
                        if (!hasRemainingChild) {
                            popoverArchParams.bodyTemplate = null;
                        }
                    }
                    break;
                }
            }
        });

        return {
            ...infoFromRootNode,
            decorationFields,
            popoverArchParams,
        };
    }
}

function parseConsolidation(attrs) {
    let consolidationMaxField;
    let consolidationMaxValue;
    const consolidationMax = attrs.consolidation_max
        ? evaluateExpr(attrs.consolidation_max)
        : {};
    if (Object.keys(consolidationMax).length > 0) {
        consolidationMaxField = Object.keys(consolidationMax)[0];
        consolidationMaxValue = consolidationMax[consolidationMaxField];
    }
    return {
        excludeField: attrs.consolidation_exclude,
        field: attrs.consolidation,
        maxField: consolidationMaxField,
        maxValue: consolidationMaxValue,
    };
}

function parseAllowedRanges(attrs) {
    const allowedRanges = new Set();
    if (attrs.scales) {
        // Unknown entries are dropped on purpose, so an untrimmed one is
        // dropped too: `scales="day, week"` used to yield the day range alone,
        // silently and with nothing in the arch to suggest it.
        for (const key of attrs.scales.split(",")) {
            if (RANGES[key.trim()]) {
                allowedRanges.add(key.trim());
            }
        }
    }
    if (allowedRanges.size === 0) {
        for (const rangeId in RANGES) {
            allowedRanges.add(rangeId);
        }
    }
    let defaultRange = attrs.default_range || attrs.default_scale;
    if (defaultRange && RANGES[defaultRange]) {
        allowedRanges.add(defaultRange);
    } else {
        defaultRange = "custom";
    }
    return { allowedRanges, defaultRange };
}

// precision = {'day': 'hour:half', 'week': 'day:half', 'month': 'day', 'year': 'month:quarter'}
function parseCellPrecisions(attrs) {
    const cellPrecisions = {};
    const precisionAttrs = attrs.precision ? evaluateExpr(attrs.precision) : {};
    for (const scaleId in SCALES) {
        if (precisionAttrs[scaleId]) {
            const precision = precisionAttrs[scaleId].split(":"); // hour:half
            // precision[0] (the cell interval) is ignored — it is not yet customizable.
            if (
                precision[1] &&
                Object.keys(SCALES[scaleId].cellPrecisions).includes(precision[1])
            ) {
                cellPrecisions[scaleId] = precision[1];
            }
        }
        cellPrecisions[scaleId] ||= SCALES[scaleId].defaultPrecision;
    }
    return cellPrecisions;
}

/** @returns {Record<string, Range>} */
function buildRanges(allowedRanges, cellPrecisions) {
    // One object per scale id, shared by every range that draws at it, so that
    // two ranges on the same granularity compare equal rather than merely alike.
    const scalesById = {};
    function getScale(scaleId) {
        if (!(scaleId in scalesById)) {
            const precision = cellPrecisions[scaleId];
            const referenceScale = SCALES[scaleId];
            scalesById[scaleId] = {
                ...omit(referenceScale, "cellPrecisions"),
                cellPart: PARTS[precision],
                cellTime: referenceScale.cellPrecisions[precision],
                id: scaleId,
                unitDescription: referenceScale.unitDescription.toString(),
            };
        }
        return scalesById[scaleId];
    }
    const ranges = {};
    for (const rangeId in RANGES) {
        if (!allowedRanges.has(rangeId)) {
            continue;
        }
        const { scaleId, description } = RANGES[rangeId];
        ranges[rangeId] = {
            id: rangeId,
            description: description.toString(),
            scale: getScale(scaleId),
        };
    }
    return ranges;
}

function parsePillDecorations(attrs) {
    let pillDecorations = null;
    for (const decoration of DECORATIONS) {
        if (decoration in attrs) {
            if (!pillDecorations) {
                pillDecorations = {};
            }
            pillDecorations[decoration] = attrs[decoration];
        }
    }
    return pillDecorations;
}

function getInfoFromRootNode(rootNode) {
    const attrs = rootNode.attrs || {};

    const {
        create: canCreate,
        delete: canDelete,
        edit: canEdit,
    } = getActiveActions(rootNode);
    const canCellCreate = exprToBoolean(attrs.cell_create, true) && canCreate;
    const canPlan = exprToBoolean(attrs.plan, true) && canEdit;
    const consolidationParams = parseConsolidation(attrs);
    const dependencyField = attrs.dependency_field || null;
    const dependencyEnabled = !!dependencyField;
    const dependencyInvertedField = attrs.dependency_inverted_field || null;
    const { allowedRanges, defaultRange } = parseAllowedRanges(attrs);
    const ranges = buildRanges(allowedRanges, parseCellPrecisions(attrs));
    const pillDecorations = parsePillDecorations(attrs);

    return {
        canCellCreate,
        canCreate,
        canDelete,
        canEdit,
        canPlan,
        colorField: attrs.color,
        computePillDisplayName: exprToBoolean(attrs.pill_label),
        consolidationParams,
        createAction: attrs.on_create || null,
        dateStartField: attrs.date_start,
        dateStopField: attrs.date_stop,
        defaultRange,
        dependencyEnabled,
        dependencyField,
        dependencyInvertedField,
        disableDrag: exprToBoolean(attrs.disable_drag_drop),
        durationField: attrs.duration_field || null,
        displayMode: attrs.display_mode || "dense",
        displayTotalRow: exprToBoolean(attrs.total_row),
        displayUnavailability: exprToBoolean(attrs.display_unavailability),
        formViewId: attrs.form_view_id ? parseInt(attrs.form_view_id, 10) : false,
        kanbanViewId: attrs.kanban_view_id ? evaluateExpr(attrs.kanban_view_id) : null,
        multiCreateView: attrs.multi_create_view || null,
        pagerLimit: attrs.groups_limit ? parseInt(attrs.groups_limit, 10) : null,
        pillDecorations,
        progressBarFields: attrs.progress_bar
            ? attrs.progress_bar
                  .split(",")
                  .map((f) => f.trim())
                  .filter(Boolean)
            : null,
        progressField: attrs.progress || null,
        ranges,
        string: attrs.string || _t("Gantt View").toString(),
        thumbnails: attrs.thumbnails ? evaluateExpr(attrs.thumbnails) : {},
        rescheduleMethods: RESCHEDULE_METHODS,
        defaultRescheduleMethod: "maintainBuffer",
    };
}
