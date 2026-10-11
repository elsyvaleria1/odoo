// @ts-check
/** @odoo-module native */

import { clamp } from "@web/core/utils/format/numbers";

export const NODE_WIDTH = 170;
export const NODE_HEIGHT = 40;

const RING_GAP = 150;
export const CANVAS_PADDING = 40;

const H_CLEARANCE = 24;
const V_CLEARANCE = 12;

export const RING_ASPECT = 0.4;

const FAN_LIMIT = 1.5 * Math.PI;

const RADIUS_STEP = 20;
const MAX_RADIUS = 20000;

export const CATEGORY_ORDER = [
    "blood",
    "affinity",
    "ritual",
    "household",
    "business",
    "agricultural",
];

const UNGROUPED = "other";

function isNearerTie(candidate, current) {
    if (candidate.fromDegree !== current.fromDegree) {
        return candidate.fromDegree < current.fromDegree;
    }
    if (candidate.weight !== current.weight) {
        return candidate.weight > current.weight;
    }
    return candidate.edgeId < current.edgeId;
}

export function primaryTies(nodes, edges) {
    const degreeById = new Map(nodes.map((node) => [node.id, node.degree]));
    const best = new Map();
    for (const edge of edges) {
        const sourceDegree = degreeById.get(edge.source);
        const targetDegree = degreeById.get(edge.target);
        if (
            sourceDegree === undefined ||
            targetDegree === undefined ||
            sourceDegree === targetDegree
        ) {
            continue;
        }
        const sourceIsInner = sourceDegree < targetDegree;
        const outerId = sourceIsInner ? edge.target : edge.source;
        const candidate = {
            parentId: sourceIsInner ? edge.source : edge.target,
            fromDegree: Math.min(sourceDegree, targetDegree),
            weight: edge.weight_risk || 0,
            edgeId: edge.id || 0,
            category: edge.category || UNGROUPED,
        };
        const current = best.get(outerId);
        if (!current || isNearerTie(candidate, current)) {
            best.set(outerId, candidate);
        }
    }
    return best;
}

export function primaryCategories(nodes, edges) {
    return new Map(
        [...primaryTies(nodes, edges)].map(([id, tie]) => [id, tie.category]),
    );
}

function overlaps(one, other, breathingRoom = 0) {
    return (
        Math.abs(one.x - other.x) < NODE_WIDTH + H_CLEARANCE + breathingRoom &&
        Math.abs(one.y - other.y) < NODE_HEIGHT + V_CLEARANCE + breathingRoom
    );
}

function anyOverlap(candidates, placed, breathingRoom = 0) {
    for (let index = 0; index < candidates.length; index += 1) {
        for (let other = index + 1; other < candidates.length; other += 1) {
            if (overlaps(candidates[index], candidates[other], breathingRoom)) {
                return true;
            }
        }
        for (const already of placed) {
            if (overlaps(candidates[index], already, breathingRoom)) {
                return true;
            }
        }
    }
    return false;
}

function onRing(angle, radius) {
    return {
        x: Math.round(Math.cos(angle) * radius),
        y: Math.round(Math.sin(angle) * radius * RING_ASPECT),
    };
}

function categoryRank(category) {
    const index = CATEGORY_ORDER.indexOf(category);
    return index === -1 ? CATEGORY_ORDER.length : index;
}

function treeAngles(nodes, ties, focusId) {
    const childrenOf = new Map();
    for (const node of nodes) {
        if (node.degree === 0) {
            continue;
        }
        const parentId = ties.get(node.id)?.parentId ?? focusId;
        const siblings = childrenOf.get(parentId);
        if (siblings) {
            siblings.push(node);
        } else {
            childrenOf.set(parentId, [node]);
        }
    }
    for (const siblings of childrenOf.values()) {
        siblings.sort(
            (one, other) =>
                categoryRank(ties.get(one.id)?.category ?? UNGROUPED) -
                    categoryRank(ties.get(other.id)?.category ?? UNGROUPED) ||
                one.id - other.id,
        );
    }

    const leafCount = new Map();
    const countLeaves = (id) => {
        if (leafCount.has(id)) {
            return leafCount.get(id);
        }
        const children = childrenOf.get(id) ?? [];
        const total = children.length
            ? children.reduce((sum, child) => sum + countLeaves(child.id), 0)
            : 1;
        leafCount.set(id, total);
        return total;
    };

    const angles = new Map();
    const assign = (id, start, end) => {
        const children = childrenOf.get(id) ?? [];
        if (!children.length) {
            return;
        }
        const total = children.reduce((sum, child) => sum + countLeaves(child.id), 0);
        let cursor = start;
        for (const child of children) {
            const width = ((end - start) * countLeaves(child.id)) / total;
            const angle = cursor + width / 2;
            angles.set(child.id, angle);
            const fan = Math.min(width, FAN_LIMIT);
            assign(child.id, angle - fan / 2, angle + fan / 2);
            cursor += width;
        }
    };
    countLeaves(focusId);
    assign(focusId, 0, 2 * Math.PI);
    return angles;
}

export function ringLayout(nodes, edges = [], breathingRoom = 0) {
    const positions = new Map();
    const focus = nodes.find((node) => node.degree === 0);
    for (const node of nodes.filter((n) => n.degree === 0)) {
        positions.set(node.id, { x: 0, y: 0 });
    }
    const outer = nodes.filter((node) => node.degree > 0);
    if (!outer.length) {
        return positions;
    }

    const ties = primaryTies(nodes, edges);
    const angles = treeAngles(nodes, ties, focus?.id);

    const placed = [{ x: 0, y: 0 }];
    let previousRadius = 0;
    const degrees = [...new Set(outer.map((node) => node.degree))].sort(
        (a, b) => a - b,
    );
    for (const degree of degrees) {
        const ring = outer.filter((node) => node.degree === degree);
        let radius = Math.max(previousRadius + RING_GAP, RING_GAP);
        let spots;
        for (;;) {
            spots = ring.map((node) => ({
                id: node.id,
                ...onRing(angles.get(node.id) ?? 0, radius),
            }));
            if (!anyOverlap(spots, placed, breathingRoom) || radius >= MAX_RADIUS) {
                break;
            }
            radius += RADIUS_STEP;
        }
        for (const spot of spots) {
            positions.set(spot.id, { x: spot.x, y: spot.y });
            placed.push(spot);
        }
        previousRadius = radius;
    }
    return positions;
}

const LABEL_CHAR_WIDTH = 6.2;
const LABEL_HEIGHT = 15;
const LABEL_PADDING = 6;

const LABEL_GAP = 10;

const LABEL_STEPS = [0, -0.08, 0.08, -0.16, 0.16, -0.26, 0.26, -0.36, 0.36];
const LABEL_OFFSETS = [0, -16, 16, -30, 30, -46, 46, -62, 62, -80, 80];

function labelBox(text) {
    return {
        width: (text || "").length * LABEL_CHAR_WIDTH + LABEL_PADDING * 2,
        height: LABEL_HEIGHT,
    };
}

function boxesHit(one, other) {
    return (
        Math.abs(one.x - other.x) < (one.width + other.width) / 2 &&
        Math.abs(one.y - other.y) < (one.height + other.height) / 2
    );
}

function halfExtentAlong(dx, dy) {
    const alongX = Math.abs(dx) ? NODE_WIDTH / 2 / Math.abs(dx) : Infinity;
    const alongY = Math.abs(dy) ? NODE_HEIGHT / 2 / Math.abs(dy) : Infinity;
    return Math.min(alongX, alongY);
}

function drawnSegment(from, to) {
    const span = Math.hypot(to.x - from.x, to.y - from.y) || 1;
    const unit = { x: (to.x - from.x) / span, y: (to.y - from.y) / span };
    const clip = halfExtentAlong(unit.x, unit.y);
    const start = { x: from.x + unit.x * clip, y: from.y + unit.y * clip };
    const end = { x: to.x - unit.x * clip, y: to.y - unit.y * clip };
    const length = Math.hypot(end.x - start.x, end.y - start.y);
    return { start, end, length, normal: { x: -unit.y, y: unit.x } };
}

function preferredDistance(edge, degreeById, segment, size) {
    const source = degreeById.get(edge.source) ?? 0;
    const target = degreeById.get(edge.target) ?? 0;
    if (source === target || segment.length < 1) {
        return 0.5;
    }
    const clear = (LABEL_GAP + size.width / 2) / segment.length;
    if (clear > 0.5) {
        return 0.5;
    }
    return source < target ? 1 - clear : clear;
}

export function labelAnchor(from, to, { distance, offset }) {
    const segment = drawnSegment(from, to);
    return {
        x:
            segment.start.x +
            (segment.end.x - segment.start.x) * distance +
            segment.normal.x * offset,
        y:
            segment.start.y +
            (segment.end.y - segment.start.y) * distance +
            segment.normal.y * offset,
    };
}

export function labelPlacements(nodes, edges, positions) {
    const degreeById = new Map(nodes.map((node) => [node.id, node.degree]));
    const nodeBoxes = nodes
        .filter((node) => positions.has(node.id))
        .map((node) => ({
            ...positions.get(node.id),
            width: NODE_WIDTH,
            height: NODE_HEIGHT,
        }));
    const placements = new Map();
    const placed = [];

    for (const edge of [...edges].sort((a, b) => (a.id || 0) - (b.id || 0))) {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) {
            continue;
        }
        const size = labelBox(edge.label);
        const segment = drawnSegment(from, to);
        const normal = segment.normal;
        const preferred = preferredDistance(edge, degreeById, segment, size);
        const distances = LABEL_STEPS.map((step) =>
            clamp(preferred + step, 0.08, 0.92),
        );

        let best = null;
        for (const distance of distances) {
            for (const offset of LABEL_OFFSETS) {
                const spot = {
                    x:
                        segment.start.x +
                        (segment.end.x - segment.start.x) * distance +
                        normal.x * offset,
                    y:
                        segment.start.y +
                        (segment.end.y - segment.start.y) * distance +
                        normal.y * offset,
                    width: size.width,
                    height: size.height,
                };
                let hits = 0;
                for (const box of nodeBoxes) {
                    if (boxesHit(spot, box)) {
                        hits += 1;
                    }
                }
                for (const box of placed) {
                    if (boxesHit(spot, box)) {
                        hits += 1;
                    }
                }
                if (!hits) {
                    best = { distance, offset, spot, hits: 0 };
                    break;
                }
                if (!best || hits < best.hits) {
                    best = { distance, offset, spot, hits };
                }
            }
            if (best && !best.hits) {
                break;
            }
        }
        placements.set(edge.id, { distance: best.distance, offset: best.offset });
        placed.push(best.spot);
    }
    return placements;
}

export function halfExtentAround(positions) {
    let x = NODE_WIDTH / 2;
    let y = NODE_HEIGHT / 2;
    for (const point of positions.values()) {
        x = Math.max(x, Math.abs(point.x) + NODE_WIDTH / 2);
        y = Math.max(y, Math.abs(point.y) + NODE_HEIGHT / 2);
    }
    return { x, y };
}

const BREATHING_ROOM = [0, 30, 60, 90];

function countLabelCollisions(nodes, edges, positions, placements) {
    const nodeBoxes = nodes
        .filter((node) => positions.has(node.id))
        .map((node) => ({
            ...positions.get(node.id),
            width: NODE_WIDTH,
            height: NODE_HEIGHT,
        }));
    const placed = [];
    let found = 0;
    for (const edge of edges) {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        const placement = placements.get(edge.id);
        if (!from || !to || !placement) {
            continue;
        }
        const box = { ...labelAnchor(from, to, placement), ...labelBox(edge.label) };
        if (
            nodeBoxes.some((node) => boxesHit(box, node)) ||
            placed.some((other) => boxesHit(box, other))
        ) {
            found += 1;
        }
        placed.push(box);
    }
    return found;
}

export function layoutNetwork(nodes, edges = []) {
    let best = null;
    for (const breathingRoom of BREATHING_ROOM) {
        const positions = ringLayout(nodes, edges, breathingRoom);
        const placements = labelPlacements(nodes, edges, positions);
        const collisions = countLabelCollisions(nodes, edges, positions, placements);
        if (!collisions) {
            return { positions, placements };
        }
        if (!best || collisions < best.collisions) {
            best = { positions, placements, collisions };
        }
    }
    return { positions: best.positions, placements: best.placements };
}

export function nodeClass(node, focusId) {
    const classes = ["o_partner_network_node"];
    if (node.id === focusId) {
        classes.push("o_partner_network_focus");
    }
    classes.push(`o_partner_network_degree_${Math.min(node.degree, 3)}`);
    if (node.is_company) {
        classes.push("o_partner_network_company");
    }
    return classes.join(" ");
}

export function labelClass(node, focusId) {
    return node.id === focusId
        ? "o_partner_network_label o_partner_network_label_focus"
        : "o_partner_network_label";
}

export function edgeClass(edge) {
    return `o_partner_network_link o_partner_network_category_${edge.category || "other"}`;
}

export function shortName(name, limit = 20) {
    return name.length > limit ? `${name.slice(0, limit - 1)}…` : name;
}

function degreesFrom(focusId, edges) {
    const neighbours = new Map();
    for (const edge of edges) {
        for (const [from, to] of [
            [edge.source, edge.target],
            [edge.target, edge.source],
        ]) {
            const bucket = neighbours.get(from);
            if (bucket) {
                bucket.push(to);
            } else {
                neighbours.set(from, [to]);
            }
        }
    }
    const degrees = new Map([[focusId, 0]]);
    let frontier = [focusId];
    for (let degree = 1; frontier.length; degree += 1) {
        const next = [];
        for (const id of frontier) {
            for (const other of neighbours.get(id) ?? []) {
                if (!degrees.has(other)) {
                    degrees.set(other, degree);
                    next.push(other);
                }
            }
        }
        frontier = next;
    }
    return degrees;
}

export function filterNetwork(network, { degree = Infinity, categories = null } = {}) {
    const allowed =
        categories === null
            ? network.edges
            : network.edges.filter((edge) => categories.has(edge.category || "other"));
    const degrees = degreesFrom(network.focus_id, allowed);
    const kept = new Set(
        [...degrees].filter(([, value]) => value <= degree).map(([id]) => id),
    );
    const nodes = network.nodes
        .filter((node) => kept.has(node.id))
        .map((node) => ({ ...node, degree: degrees.get(node.id) }));
    const edges = allowed.filter(
        (edge) => kept.has(edge.source) && kept.has(edge.target),
    );
    return { ...network, nodes, edges };
}
