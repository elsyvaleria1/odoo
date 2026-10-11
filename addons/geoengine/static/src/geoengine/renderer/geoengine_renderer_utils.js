/** @odoo-module native */
import { appContextOf } from "@web/core/app_context";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/translation";

import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";

const debugLog = makeGeoLogger("RendererUtils");

const MAX_FIT_ZOOM = 15;
const FIT_PADDING = [50, 50, 50, 50];

/**
 * @param {Object|string} geojson
 * @returns {string}
 */
export function detectGeoJSONProjection(geojson) {
    try {
        const obj = typeof geojson === "string" ? JSON.parse(geojson) : geojson;
        const crsName = obj?.crs?.properties?.name;
        if (crsName) {
            if (crsName.startsWith("EPSG:")) {
                return crsName;
            }
            const match = crsName.match(/EPSG::?(\d+)/);
            if (match) {
                return `EPSG:${match[1]}`;
            }
        }
    } catch {}
    return "EPSG:4326";
}

export class GeoengineRendererUtils {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
    }
    addMoveEndListenerToMap() {
        this._zoomKey = `geoengine.zoom.${this.renderer.layerScope}`;
        this._moveEndHandler = () => {
            const newZoom = this.renderer.map.getView().getZoom();
            debugLog("Map moveend event, zoom:", newZoom);
            try {
                browser.localStorage.setItem(this._zoomKey, String(newZoom));
            } catch (error) {
                debugLog("Zoom not remembered: storage is unavailable", error);
            }
        };
        this.renderer.map.on("moveend", this._moveEndHandler);
    }

    /**
     * @returns {number|null}
     */
    getStoredZoom() {
        let raw = null;
        try {
            raw = browser.localStorage.getItem(
                this._zoomKey || `geoengine.zoom.${this.renderer.layerScope}`,
            );
        } catch (error) {
            debugLog("Stored zoom unreadable: storage is unavailable", error);
        }
        const zoom = raw === null ? NaN : Number(raw);
        return Number.isFinite(zoom) ? zoom : null;
    }

    removeMoveEndListener() {
        if (this._moveEndHandler && this.renderer.map) {
            this.renderer.map.un("moveend", this._moveEndHandler);
            this._moveEndHandler = null;
        }
    }

    createOverlay() {
        const popupElement = this.renderer.popupRef.el;
        this.renderer.overlay = new ol.Overlay({
            element: popupElement,
            autoPan: false,
        });
    }

    getOriginalZoom() {
        const mapView = this.renderer.map.getView();
        if (!mapView) {
            return;
        }

        const extent = this._featuresExtent() || this._configuredExtent();
        if (!extent) {
            debugLog("No features and no configured extent; leaving the view as is");
            return;
        }
        mapView.fit(extent, {
            maxZoom: MAX_FIT_ZOOM,
            padding: FIT_PADDING,
        });
    }

    /**
     * The map frames what the search filtered, and a search only ever filters
     * the view's own model. A cross-model layer ignores the view's domain by
     * construction (GeoengineModel._effectiveLayerDomain), so letting it into
     * the extent makes a search for a single record frame every record of the
     * other model instead -- the filtered record is then one pin among
     * hundreds that did not move. Such a layer stays drawn as context; it just
     * stops driving the fit. Falls back to every layer when the view's model
     * put nothing on the map, so an overlay-only map still frames itself.
     *
     * @returns {number[]|null}
     */
    _featuresExtent() {
        const layers = this.renderer.vectorLayersResult || [];
        return this._extentOf(this._viewModelLayers(layers)) || this._extentOf(layers);
    }

    /**
     * @param {Array<ol.layer.Vector>} layers
     * @returns {Array<ol.layer.Vector>}
     */
    _viewModelLayers(layers) {
        const resModel = this.renderer.props.model.root?.resModel;
        if (!resModel) {
            return [];
        }
        const configs = new Map(
            (this.renderer.props.model.layers?.vectors || []).map((config) => [
                config.resId,
                config,
            ]),
        );
        return layers.filter((layer) => {
            const config = configs.get(layer.get("layerId"));
            return config && (!config.model || config.model === resModel);
        });
    }

    /**
     * @param {Array<ol.layer.Vector>} layers
     * @returns {number[]|null}
     */
    _extentOf(layers) {
        let combined = null;
        for (const layer of layers) {
            const source = layer.getSource();
            const extent =
                layer.get("dataExtent") ||
                (source?.getFeatures?.().length ? source.getExtent() : null);
            if (!extent || ol.extent.isEmpty(extent)) {
                continue;
            }
            combined = combined ? ol.extent.extend(combined, extent) : extent.slice();
        }
        return combined;
    }

    /**
     * @returns {boolean}
     */
    fitConfiguredExtent() {
        const extent = this._configuredExtent();
        if (!extent) {
            return false;
        }
        this.renderer.map.getView().fit(extent, {
            maxZoom: MAX_FIT_ZOOM,
            padding: FIT_PADDING,
        });
        return true;
    }

    /**
     * @returns {number[]|null}
     */
    _configuredExtent() {
        return this.renderer.props.model.getMapConfig().defaultExtent || null;
    }

    showMissingLayersWarning() {
        if (this.renderer.missingLayersWarningShown) {
            return;
        }
        this.renderer.missingLayersWarningShown = true;

        const message = _t(
            "This geoengine view is missing vector layer configuration. " +
                "Please configure at least one vector layer for this view to display data on the map.",
        );

        if (appContextOf(this.renderer).services.notification) {
            appContextOf(this.renderer).services.notification.add(message, {
                title: _t("Missing Map Configuration"),
                type: "warning",
                sticky: false,
            });
        } else {
            console.warn("GeoengineRenderer:", message);
        }
    }
}
