/** @odoo-module native */
import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";
import { withOpacity } from "../classification.js";

const debugLog = makeGeoLogger("RendererTrails");
export class GeoengineRendererTrails {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;

        this.trailStore = new Map();

        this.trailLayers = new Map();

        this.defaultConfig = {
            maxLength: 50,
            maxAge: 3600000,
            color: "#0000FF",
            width: 2,
            opacity: 0.6,
        };

        debugLog("GeoengineRendererTrails initialized");
    }

    /**
     * @param {string} model
     * @param {number} recordId
     * @param {Object} geometry
     * @param {Date} timestamp
     */
    addPosition(model, recordId, geometry, timestamp = new Date()) {
        if (typeof geometry === "string") {
            try {
                geometry = JSON.parse(geometry);
            } catch {
                debugLog("addPosition: unparseable geometry", geometry);
                return;
            }
        }
        if (!geometry?.coordinates) {
            debugLog("addPosition: no coordinates", geometry);
            return;
        }
        if (!this.trailStore.has(model)) {
            this.trailStore.set(model, new Map());
        }

        const modelTrails = this.trailStore.get(model);

        if (!modelTrails.has(recordId)) {
            modelTrails.set(recordId, []);
        }

        const trail = modelTrails.get(recordId);

        trail.push({
            geometry,
            timestamp,
        });

        debugLog(`Trail position added: ${model}/${recordId}`, {
            trailLength: trail.length,
            timestamp,
        });

        this._cleanupTrail(model, recordId);

        this.renderTrail(model, recordId);
    }

    /**
     * @param {string} model
     * @param {number} recordId
     */
    renderTrail(model, recordId) {
        if (!this.renderer.map) {
            return;
        }
        const layerId = `trail_${model}`;
        if (!this.trailLayers.has(layerId)) {
            const layer = this.createTrailLayer({
                resId: model,
                name: model,
                sequence: 0,
                trail_color: this.defaultConfig.color,
                trail_width: this.defaultConfig.width,
                trail_opacity: this.defaultConfig.opacity,
            });
            this.trailLayers.set(layerId, layer);
            this.renderer.map.addLayer(layer);
        }
        this.updateTrailLayer(model, recordId, layerId);
    }

    /**
     * @param {string} model
     * @param {number} recordId
     */
    _cleanupTrail(model, recordId) {
        const modelTrails = this.trailStore.get(model);
        if (!modelTrails) {
            return;
        }

        const trail = modelTrails.get(recordId);
        if (!trail) {
            return;
        }

        const config = this.defaultConfig;
        const now = Date.now();

        let validTrail = trail.filter((pos) => {
            const age = now - pos.timestamp.getTime();
            return age <= config.maxAge;
        });

        if (validTrail.length > config.maxLength) {
            validTrail = validTrail.slice(-config.maxLength);
        }

        modelTrails.set(recordId, validTrail);

        debugLog(
            `Trail cleaned: ${model}/${recordId} - ${trail.length} → ${validTrail.length}`,
        );
    }

    /**
     * @param {string} model
     * @param {number} recordId
     * @returns {Array|null}
     */
    getTrail(model, recordId) {
        const modelTrails = this.trailStore.get(model);
        if (!modelTrails) {
            return null;
        }

        return modelTrails.get(recordId) || null;
    }

    /**
     * @param {Object} vectorConfig
     * @returns {ol.layer.Vector}
     */
    createTrailLayer(vectorConfig) {
        const layerId = `trail_${vectorConfig.resId}`;

        if (this.trailLayers.has(layerId)) {
            return this.trailLayers.get(layerId);
        }

        const trailLayer = new ol.layer.Vector({
            title: `Trail: ${vectorConfig.name}`,
            source: new ol.source.Vector({
                features: [],
            }),
            style: this._createTrailStyle(vectorConfig),
            zIndex: vectorConfig.sequence - 1,
            renderBuffer: 100,
            updateWhileAnimating: true,
            updateWhileInteracting: true,
        });

        this.trailLayers.set(layerId, trailLayer);
        debugLog(`Trail layer created: ${layerId}`);

        return trailLayer;
    }

    /**
     * @param {Object} config
     * @returns {ol.style.Style}
     */
    _createTrailStyle(config) {
        const color = config.trail_color || this.defaultConfig.color;
        const width = config.trail_width || this.defaultConfig.width;
        const opacity = config.trail_opacity || this.defaultConfig.opacity;

        const rgbaColor = withOpacity(color, opacity);

        return new ol.style.Style({
            stroke: new ol.style.Stroke({
                color: rgbaColor,
                width: width,
                lineCap: "round",
                lineJoin: "round",
            }),
        });
    }

    /**
     * @param {string} model
     * @param {number} recordId
     * @param {string} layerId
     */
    updateTrailLayer(model, recordId, layerId) {
        const trailLayer = this.trailLayers.get(layerId);
        if (!trailLayer) {
            debugLog(`Trail layer not found: ${layerId}`);
            return;
        }

        const trail = this.getTrail(model, recordId);
        if (!trail || trail.length < 2) {
            return;
        }

        const source = trailLayer.getSource();

        let trailFeature = source.getFeatureById(recordId);

        const coordinates = trail.map((pos) => pos.geometry.coordinates);
        const geojson = {
            type: "Feature",
            geometry: {
                type: "LineString",
                coordinates: coordinates,
            },
            properties: {
                recordId: recordId,
                model: model,
            },
        };

        const format = new ol.format.GeoJSON();
        const feature = format.readFeature(geojson, {
            dataProjection: "EPSG:4326",
            featureProjection: this.renderer.map.getView().getProjection(),
        });

        const lineString = feature.getGeometry();

        if (trailFeature) {
            trailFeature.setGeometry(lineString);
            debugLog(`Trail updated: ${model}/${recordId}`, {
                points: coordinates.length,
            });
        } else {
            trailFeature = new ol.Feature({
                geometry: lineString,
                recordId: recordId,
                model: model,
            });
            trailFeature.setId(recordId);
            source.addFeature(trailFeature);
            debugLog(`Trail created: ${model}/${recordId}`, {
                points: coordinates.length,
            });
        }
    }

    cleanup() {
        this.trailStore.clear();
        this.trailLayers.clear();
        debugLog("All trails cleaned up");
    }
}
