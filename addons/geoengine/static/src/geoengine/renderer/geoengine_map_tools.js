/** @odoo-module native */

import { _t } from "@web/core/translation";

import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";

const debugLog = makeGeoLogger("MapTools");

const MEASURE_COLOR = "rgba(255, 104, 10, 1)";
const MEASURE_FILL = "rgba(255, 104, 10, 0.15)";

/**
 * @param {number} metres
 * @returns {string}
 */
export function formatLength(metres) {
    if (metres >= 1000) {
        return `${(metres / 1000).toFixed(2)} km`;
    }
    return `${metres.toFixed(0)} m`;
}

/**
 * @param {number} squareMetres
 * @returns {string}
 */
export function formatArea(squareMetres) {
    if (squareMetres >= 1e6) {
        return `${(squareMetres / 1e6).toFixed(2)} km²`;
    }
    if (squareMetres >= 1e4) {
        return `${(squareMetres / 1e4).toFixed(2)} ha`;
    }
    return `${squareMetres.toFixed(0)} m²`;
}

export class GeoengineMapTools {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
        this._overlays = [];
        this._interactions = [];
        this._geolocation = null;
        this._measureLayer = null;
        this._measureDraw = null;
        this._snaps = [];
    }

    /** @returns {ol.Map} */
    get map() {
        return this.renderer.map;
    }

    /** @returns {boolean} */
    get isMeasuring() {
        return Boolean(this._measureDraw);
    }

    /**
     * @param {"line"|"polygon"} [kind="line"]
     */
    createMeasureControl(kind = "line") {
        const isArea = kind === "polygon";
        const { element, button } = this.renderer.interactions.createHtmlControl(
            isArea
                ? '<i class="fa-solid fa-draw-polygon"></i>'
                : '<i class="fa-solid fa-ruler"></i>',
            `measure-control measure-${kind} ol-unselectable ol-control`,
        );
        button.title = isArea ? _t("Measure area") : _t("Measure distance");

        button.addEventListener("click", () => {
            if (this._measureDraw) {
                this.stopMeasuring();
                return;
            }
            this.startMeasuring(kind);
            button.classList.add("selected-control");
        });

        this.map.addControl(new ol.control.Control({ element }));
    }

    /**
     * @param {"line"|"polygon"} kind
     */
    startMeasuring(kind) {
        this.stopMeasuring();

        const source = new ol.source.Vector();
        this._measureLayer = new ol.layer.Vector({
            source,
            zIndex: 9999,
            style: new ol.style.Style({
                fill: new ol.style.Fill({ color: MEASURE_FILL }),
                stroke: new ol.style.Stroke({
                    color: MEASURE_COLOR,
                    width: 2,
                    lineDash: [8, 6],
                }),
                image: new ol.style.Circle({
                    radius: 4,
                    fill: new ol.style.Fill({ color: MEASURE_COLOR }),
                }),
            }),
        });
        this.map.addLayer(this._measureLayer);

        this._measureDraw = new ol.interaction.Draw({
            source,
            type: kind === "polygon" ? "Polygon" : "LineString",
        });
        this.map.addInteraction(this._measureDraw);
        this._interactions.push(this._measureDraw);

        this._measureDraw.on("drawstart", (event) => {
            const geometry = event.feature.getGeometry();
            const tooltip = this._createMeasureTooltip();
            const onChange = () => {
                tooltip.element.textContent = this._measureText(geometry);
                tooltip.overlay.setPosition(this._labelAnchor(geometry));
            };
            onChange();
            geometry.on("change", onChange);
            this._activeSketch = { geometry, onChange };
        });

        this._measureDraw.on("drawend", () => {
            if (this._activeSketch) {
                this._activeSketch.geometry.un("change", this._activeSketch.onChange);
                this._activeSketch = null;
            }
        });
    }

    stopMeasuring() {
        if (this._activeSketch) {
            this._activeSketch.geometry.un("change", this._activeSketch.onChange);
            this._activeSketch = null;
        }
        if (this._measureDraw) {
            this.map.removeInteraction(this._measureDraw);
            this._interactions = this._interactions.filter(
                (i) => i !== this._measureDraw,
            );
            this._measureDraw = null;
        }
        if (this._measureLayer) {
            this.map.removeLayer(this._measureLayer);
            this._measureLayer.getSource()?.clear();
            this._measureLayer = null;
        }
        for (const overlay of this._overlays.splice(0)) {
            this.map.removeOverlay(overlay);
        }
        for (const el of this.renderer.mapRef.el?.querySelectorAll(
            ".o_geo_measure_tooltip",
        ) ?? []) {
            el.remove();
        }
        for (const button of this.renderer.mapRef.el?.querySelectorAll(
            ".measure-control button",
        ) ?? []) {
            button.classList.remove("selected-control");
        }
    }

    /**
     * @param {ol.geom.Geometry} geometry
     * @returns {string}
     */
    _measureText(geometry) {
        const projection = this.map.getView().getProjection();
        if (geometry.getType() === "Polygon") {
            return formatArea(ol.sphere.getArea(geometry, { projection }));
        }
        return formatLength(ol.sphere.getLength(geometry, { projection }));
    }

    /**
     * @param {ol.geom.Geometry} geometry
     * @returns {Array<number>}
     */
    _labelAnchor(geometry) {
        if (geometry.getType() === "Polygon") {
            return geometry.getInteriorPoint().getCoordinates();
        }
        return geometry.getLastCoordinate();
    }

    /**
     * @returns {{element: HTMLElement, overlay: ol.Overlay}}
     */
    _createMeasureTooltip() {
        const element = document.createElement("div");
        element.className = "o_geo_measure_tooltip";
        const overlay = new ol.Overlay({
            element,
            offset: [0, -12],
            positioning: "bottom-center",
            stopEvent: false,
        });
        this.map.addOverlay(overlay);
        this._overlays.push(overlay);
        return { element, overlay };
    }

    createGeolocateControl() {
        const { element, button } = this.renderer.interactions.createHtmlControl(
            '<i class="fa-solid fa-location-crosshairs"></i>',
            "geolocate-control ol-unselectable ol-control",
        );
        button.title = _t("Show my position");

        button.addEventListener("click", () => this.locate());
        this.map.addControl(new ol.control.Control({ element }));
    }

    locate() {
        if (!this._geolocation) {
            this._geolocation = new ol.Geolocation({
                trackingOptions: { enableHighAccuracy: true },
                projection: this.map.getView().getProjection(),
            });

            this._geolocation.on("error", (error) => {
                debugLog("geolocation error", error);
                this.renderer.notification.add(
                    _t("Could not determine your position: %s", error.message),
                    { type: "warning" },
                );
                this._geolocation.setTracking(false);
            });

            this._geolocation.on("change:position", () => {
                const position = this._geolocation.getPosition();
                if (!position) {
                    return;
                }
                this._showPosition(position, this._geolocation.getAccuracy());
                this._geolocation.setTracking(false);
            });
        }
        this._geolocation.setTracking(true);
    }

    /**
     * @param {Array<number>} position
     * @param {number} [accuracy]
     */
    _showPosition(position, accuracy) {
        if (!this._positionLayer) {
            this._positionSource = new ol.source.Vector();
            this._positionLayer = new ol.layer.Vector({
                source: this._positionSource,
                zIndex: 9998,
                style: new ol.style.Style({
                    image: new ol.style.Circle({
                        radius: 7,
                        fill: new ol.style.Fill({ color: "rgba(51, 136, 255, 0.9)" }),
                        stroke: new ol.style.Stroke({ color: "#fff", width: 2 }),
                    }),
                }),
            });
            this.map.addLayer(this._positionLayer);
        }
        this._positionSource.clear();
        this._positionSource.addFeature(
            new ol.Feature({ geometry: new ol.geom.Point(position) }),
        );
        this.map.getView().animate({ center: position, zoom: 17, duration: 400 });
        if (accuracy) {
            this.renderer.notification.add(
                _t("Position found, accurate to about %s m", Math.round(accuracy)),
                { type: "info" },
            );
        }
    }

    enableBoxSelect() {
        const dragBox = new ol.interaction.DragBox({
            condition: ol.events.condition.platformModifierKeyOnly,
        });
        this.map.addInteraction(dragBox);
        this._interactions.push(dragBox);

        dragBox.on("boxend", () => {
            // A WebGL map has no click Select (it cannot restyle a feature),
            // so the box keeps its own collection there: counting and the
            // single-feature popup still work, only the highlight does not.
            const selection =
                this.renderer.selectClick?.getFeatures() ??
                (this._boxSelection ??= new ol.Collection());
            const extent = dragBox.getGeometry().getExtent();
            selection.clear();

            for (const layer of this.renderer.vectorLayersResult ?? []) {
                const source = layer.getSource?.();
                const realSource = source?.getSource?.() ?? source;
                if (!realSource?.forEachFeatureIntersectingExtent) {
                    continue;
                }
                realSource.forEachFeatureIntersectingExtent(extent, (feature) => {
                    selection.push(feature);
                });
            }

            const count = selection.getLength();
            debugLog(`box select: ${count} feature(s)`);

            if (count === 1) {
                this.renderer.interactions.updateInfoBox(selection);
            } else if (count > 1) {
                this.renderer.interactions.hidePopup();
                this.renderer.notification.add(_t("%s features selected", count), {
                    type: "info",
                });
            }
        });
    }

    /**
     * @param {Array<ol.layer.Vector>} layers
     */
    attachSnap(layers) {
        this.detachSnap();
        for (const layer of layers ?? []) {
            const source = layer.getSource?.();
            if (!source?.getFeatures || source.getSource) {
                continue;
            }
            const snap = new ol.interaction.Snap({ source });
            this.map.addInteraction(snap);
            this._snaps.push(snap);
        }
        debugLog(`snap attached to ${this._snaps.length} layer(s)`);
    }

    detachSnap() {
        for (const snap of this._snaps.splice(0)) {
            this.map.removeInteraction(snap);
        }
    }

    createExportControl() {
        const { element, button } = this.renderer.interactions.createHtmlControl(
            '<i class="fa-solid fa-camera"></i>',
            "export-control ol-unselectable ol-control",
        );
        button.title = _t("Export map as image");

        button.addEventListener("click", () => this.exportPng());
        this.map.addControl(new ol.control.Control({ element }));
    }

    exportPng() {
        this.map.once("rendercomplete", () => {
            try {
                const target = this._compositeCanvas();
                if (!target) {
                    throw new Error("no canvas to export");
                }
                target.toBlob((blob) => {
                    if (!blob) {
                        this.renderer.notification.add(
                            _t("The map could not be exported."),
                            { type: "danger" },
                        );
                        return;
                    }
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "map.png";
                    link.click();
                    URL.revokeObjectURL(url);
                });
            } catch (error) {
                debugLog("export failed", error);
                this.renderer.notification.add(
                    _t("The map could not be exported: %s", error.message),
                    { type: "danger" },
                );
            }
        });
        this.map.renderSync();
    }

    /**
     * @returns {HTMLCanvasElement|null}
     */
    _compositeCanvas() {
        const size = this.map.getSize();
        if (!size) {
            return null;
        }
        const target = document.createElement("canvas");
        target.width = size[0];
        target.height = size[1];
        const context = target.getContext("2d");

        const canvases =
            this.renderer.mapRef.el?.querySelectorAll(".ol-layer canvas") ?? [];
        for (const canvas of canvases) {
            if (!canvas.width || !canvas.height) {
                continue;
            }
            const { opacity, filter, transform } = canvas.parentNode.style;
            context.globalAlpha = opacity === "" ? 1 : Number(opacity);
            context.filter = filter || "none";
            const matrix = transform
                ? transform
                      .match(/^matrix\(([^)]*)\)$/)?.[1]
                      .split(",")
                      .map(Number)
                : null;
            if (matrix) {
                context.setTransform(...matrix);
            } else {
                context.setTransform(1, 0, 0, 1, 0, 0);
            }
            context.drawImage(canvas, 0, 0);
        }
        context.globalAlpha = 1;
        context.setTransform(1, 0, 0, 1, 0, 0);
        return target;
    }

    teardown() {
        this.stopMeasuring();
        this.detachSnap();
        for (const interaction of this._interactions.splice(0)) {
            this.map?.removeInteraction(interaction);
        }
        for (const overlay of this._overlays.splice(0)) {
            this.map?.removeOverlay(overlay);
        }
        if (this._geolocation) {
            this._geolocation.setTracking(false);
            this._geolocation = null;
        }
        if (this._positionLayer) {
            this.map?.removeLayer(this._positionLayer);
            this._positionLayer = null;
            this._positionSource = null;
        }
    }
}
