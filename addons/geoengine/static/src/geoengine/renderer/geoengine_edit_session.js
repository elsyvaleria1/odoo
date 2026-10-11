/** @odoo-module native */

import { ol } from "../../lib/geo_libs.js";

const PROBLEM_COLOR = "rgba(220, 53, 69, 0.95)";

/**
 * The reshapes of one editing session, undone and redone in order. An entry
 * names the record and field it changed, not the map feature: a save redraws
 * the layers, and an undo then reaches the record through the view's list.
 *
 * @typedef {{resId: number, geoField: string, before: ol.geom.Geometry, after: ol.geom.Geometry}} EditStep
 */
export class EditHistory {
    constructor() {
        this._done = [];
        this._undone = [];
    }

    /**
     * @param {EditStep} step
     */
    record(step) {
        this._done.push(step);
        this._undone = [];
    }

    /**
     * @returns {EditStep|undefined}
     */
    undo() {
        const step = this._done.pop();
        if (step) {
            this._undone.push(step);
        }
        return step;
    }

    /**
     * @returns {EditStep|undefined}
     */
    redo() {
        const step = this._undone.pop();
        if (step) {
            this._done.push(step);
        }
        return step;
    }

    clear() {
        this._done = [];
        this._undone = [];
    }

    get canUndo() {
        return this._done.length > 0;
    }

    get canRedo() {
        return this._undone.length > 0;
    }
}

/**
 * The key a keydown means for the active tool, or null.
 *
 * @param {KeyboardEvent} event
 * @param {"draw"|"modify"|"select"} tool
 * @returns {"undo"|"redo"|"remove-last-point"|"abort"|null}
 */
export function editCommandOf(event, tool) {
    const target = event.target;
    if (target?.closest?.("input, textarea, [contenteditable]")) {
        return null;
    }
    const key = event.key.toLowerCase();
    const command = event.ctrlKey || event.metaKey;
    if (tool === "draw") {
        if ((command && key === "z") || key === "backspace") {
            return "remove-last-point";
        }
        return key === "escape" ? "abort" : null;
    }
    if (tool !== "modify" || !command) {
        return null;
    }
    if (key === "y" || (key === "z" && event.shiftKey)) {
        return "redo";
    }
    return key === "z" ? "undo" : null;
}

/**
 * How many parts a geometry has: a Multi* geometry's members, else one.
 *
 * @param {ol.geom.Geometry|undefined} geometry
 * @returns {number}
 */
export function partCount(geometry) {
    switch (geometry?.getType()) {
        case undefined:
            return 0;
        case "MultiPolygon":
            return geometry.getPolygons().length;
        case "MultiLineString":
            return geometry.getLineStrings().length;
        case "MultiPoint":
            return geometry.getPoints().length;
        default:
            return 1;
    }
}

export class ProblemMarker {
    /**
     * @param {ol.Map} map
     */
    constructor(map) {
        this._source = new ol.source.Vector();
        this._layer = new ol.layer.Vector({
            source: this._source,
            zIndex: 10000,
            style: new ol.style.Style({
                stroke: new ol.style.Stroke({
                    color: PROBLEM_COLOR,
                    width: 2,
                    lineDash: [6, 4],
                }),
                image: new ol.style.Circle({
                    radius: 9,
                    fill: new ol.style.Fill({ color: "rgba(220, 53, 69, 0.2)" }),
                    stroke: new ol.style.Stroke({ color: PROBLEM_COLOR, width: 3 }),
                }),
            }),
        });
        map.addLayer(this._layer);
        this._map = map;
    }

    /**
     * @param {Array<number>|null} location
     * @param {ol.geom.Geometry} [shape] the shape as drawn, kept in view
     */
    show(location, shape) {
        this._source.clear();
        if (shape) {
            this._source.addFeature(new ol.Feature({ geometry: shape.clone() }));
        }
        if (location) {
            this._source.addFeature(
                new ol.Feature({ geometry: new ol.geom.Point(location) }),
            );
        }
    }

    clear() {
        this._source.clear();
    }

    get location() {
        const point = this._source
            .getFeatures()
            .map((feature) => feature.getGeometry())
            .find((geometry) => geometry.getType() === "Point");
        return point ? point.getCoordinates() : null;
    }

    destroy() {
        this._map.removeLayer(this._layer);
    }
}
