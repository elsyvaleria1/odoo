/** @odoo-module native */
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

import { makeGeoLogger } from "../geo_debug.js";
import { ol } from "../lib/geo_libs.js";
import { DEFAULT_TRAIL_COLOR } from "./classification.js";
import { GeoengineRecord } from "./geoengine_record.js";
import { LayersPanel } from "./panels/layers_panel.js";
import { TimeSlider } from "./panels/time_slider.js";
import { savedValue } from "./record_values.js";
import { GeoengineMapTools } from "./renderer/geoengine_map_tools.js";
import { GeoengineRendererInteractions } from "./renderer/geoengine_renderer_interactions.js";
import { GeoengineRendererLayers } from "./renderer/geoengine_renderer_layers.js";
import { GeoengineRendererStyling } from "./renderer/geoengine_renderer_styling.js";
import { GeoengineRendererTrails } from "./renderer/geoengine_renderer_trails.js";
import { GeoengineRendererUtils } from "./renderer/geoengine_renderer_utils.js";
import { GeoengineSpatialFilter } from "./renderer/geoengine_spatial_filter.js";
import { RasterLayerBuilder } from "./renderer/raster_layers.js";
import { TrailLayerBuilder } from "./renderer/trail_layer.js";

const debugLog = makeGeoLogger("GeoengineRenderer");
const log = debugLog.log;

export class GeoengineRenderer extends Component {
    static template = "geoengine.GeoengineRenderer";
    static props = {
        model: t.object(),
        archInfo: t.object(),
        openRecord: t.function(),
        geoFieldKey: t.or([t.string(), t.literal(false)]).optional(),
        createRecord: t.function().optional(),
        updateRecord: t.function().optional(),
        onDrawStart: t.function().optional(),
        onClickDiscard: t.function().optional(),
    };
    static components = { LayersPanel, GeoengineRecord, TimeSlider };
    props = useProps(this.constructor.props);
    setup() {
        useLifecycleLog(log);
        this.state = proxy({
            selectedFeatures: [],
            popup: null,
            popupList: null,
            isModified: false,
            showTimeSlider: false,
            timeSliderMin: 0,
            timeSliderMax: 0,
            timeSliderKey: 0,
            trailColor: DEFAULT_TRAIL_COLOR,
        });
        this.isFit = false;
        this.isFitToConfiguredExtent = false;
        this.webglTrailLayer = null;

        this.layerScope = this.props.model.layerScope;

        this.mapRef = elementRef();
        this.popupRef = elementRef();
        this.popupContentRef = elementRef();
        this.legendRef = elementRef();
        debugLog("State initialized");

        this.notification = useService("notification");
        this.action = useService("action");

        this.layers = new GeoengineRendererLayers(this);
        this.rasters = new RasterLayerBuilder(this);
        this.trail = new TrailLayerBuilder(this);

        this.styling = new GeoengineRendererStyling(this);

        this.interactions = new GeoengineRendererInteractions(this);

        this.utils = new GeoengineRendererUtils(this);

        this.trails = new GeoengineRendererTrails(this);

        this.mapTools = new GeoengineMapTools(this);

        this.spatialFilter = new GeoengineSpatialFilter(this);

        debugLog("Modules initialized (Layers, Styling, Interactions, Utils, Trails)");

        onWillStart(async () => {
            this.isGeoengineAdmin = await user.hasGroup(
                "geoengine.group_geoengine_admin",
            );
            debugLog("✅ Permissions checked, is admin:", this.isGeoengineAdmin);
        });

        onMounted(async () => {
            debugLog("🟢 [RENDERER] ============ onMounted() START ============");

            const vectors = this.props.model.layers.vectors;
            debugLog("🟢 [RENDERER] Vector layers for this view:", {
                scope: this.layerScope,
                count: vectors.length,
                layers: vectors.map((l) => ({ name: l.name })),
            });

            debugLog("🟢 [RENDERER] Creating map instance");
            this.renderMap();
            debugLog("🟢 [RENDERER] Map instance created");

            debugLog("🟢 [RENDERER] ============ onMounted() COMPLETE ============");
        });

        onWillUnmount(() => {
            debugLog("Component unmounting - starting cleanup");
            this.cleanupResources();
        });

        useLayoutEffect(
            () => {
                debugLog(
                    "🟣 [RENDERER] ============ useLayoutEffect TRIGGERED ============",
                    {
                        hasMap: !!this.map,
                        isModified: this.state.isModified,
                        hasData: !!this.props.model.root.data,
                    },
                );

                if (this.state.isModified && !this.props.model.root.editedRecord) {
                    this.state.isModified = false;
                }

                if (!this.state.isModified && this.props.model.root.data) {
                    debugLog(
                        "🟣 [RENDERER] useLayoutEffect conditions met - calling renderVectorLayers()",
                    );
                    this.renderVectorLayers();
                    debugLog(
                        "🟣 [RENDERER] useLayoutEffect renderVectorLayers() complete",
                    );
                } else {
                    debugLog(
                        "🟣 [RENDERER] useLayoutEffect conditions NOT met - skipping render",
                        {
                            hasMap: !!this.map,
                            isModified: this.state.isModified,
                            hasData: !!this.props.model.root.data,
                        },
                    );
                }
            },
            () => [this.props.model.root.data, this.props.model.root.editedRecord],
        );
    }

    renderMap() {
        debugLog("renderMap() - Called, map exists:", !!this.map);
        if (this.map) {
            return;
        }
        const endMap = log.perf("renderMap");
        debugLog("renderMap() - Creating map for the first time");
        this.utils.createOverlay();
        const mapElement = this.mapRef.el;
        debugLog("renderMap() - Map element found:", !!mapElement);

        const mapConfig = this.props.model.getMapConfig();
        const viewOptions = {
            center: ol.proj.fromLonLat([0, 0]),
            zoom: mapConfig.defaultZoom || 2,
            projection: mapConfig.projection,
        };
        if (mapConfig.restrictedExtent) {
            viewOptions.extent = mapConfig.restrictedExtent;
        }

        this.map = new ol.Map({
            target: mapElement,
            layers: [
                new ol.layer.Group({
                    title: "Base maps",
                    layers: this.rasters.createBackgroundLayers(
                        this.props.model.layers.rasters,
                    ),
                }),
            ],
            overlays: [this.overlay],
            view: new ol.View(viewOptions),
            controls: this._buildControls(mapConfig.controls),
        });
        debugLog("renderMap() - Map created successfully");

        this.utils.addMoveEndListenerToMap();
        debugLog("renderMap() - Event listeners added");

        this.format = new ol.format.GeoJSON({
            dataProjection: this.map.getView().getProjection(),
        });

        this.setupControls();
        endMap();
    }

    /**
     * @param {Object} [controls]
     * @returns {Array<ol.control.Control>}
     */
    _buildControls(controls = {}) {
        const list = [
            new ol.control.Zoom(),
            new ol.control.Rotate(),
            new ol.control.ScaleLine(),
        ];
        if (controls.attribution !== false) {
            list.push(new ol.control.Attribution({ collapsible: true }));
        }
        if (controls.fullscreen !== false) {
            list.push(new ol.control.FullScreen());
        }
        if (controls.zoom_slider) {
            list.push(new ol.control.ZoomSlider());
        }
        if (controls.overview_map) {
            list.push(
                new ol.control.OverviewMap({
                    collapsed: true,
                    layers: [new ol.layer.Tile({ source: new ol.source.OSM() })],
                }),
            );
        }
        if (controls.mouse_position) {
            list.push(
                new ol.control.MousePosition({
                    coordinateFormat: (coordinate) =>
                        coordinate?.map((n) => n.toFixed(2)).join(", ") ?? "",
                    className: "o_geo_mouse_position",
                }),
            );
        }
        debugLog(`Map controls: ${list.length}`);
        return list;
    }

    setupControls() {
        this.mapTools.createMeasureControl("line");
        this.mapTools.createMeasureControl("polygon");
        this.mapTools.createGeolocateControl();
        this.mapTools.createExportControl();
        this.spatialFilter.createControl();
        this.mapTools.enableBoxSelect();

        if (this.props.archInfo.editable && this.isGeoengineAdmin) {
            this.interactions.createDrawControl();
            this.interactions.createSelectControl();
            this.interactions.createEditControl();
            this.interactions.createUndoControl();
        }
    }

    /**
     * @param {Object} record
     */
    onDisplayPopupRecord(record) {
        this.interactions.onDisplayPopupRecord(record);
    }

    /**
     * @param {Object} record
     */
    zoomOnFeature(record) {
        this.interactions.zoomOnFeature(record);
    }

    /**
     * @param {Object[]} records
     */
    zoomToRecords(records) {
        this.interactions.zoomToRecords(records);
    }

    get cellListTitle() {
        return _t("%s records at this spot", this.state.popupList.count);
    }

    get cellListMore() {
        return _t(
            "Only the first %s are listed. Narrow the search to see the others.",
            this.state.popupList.records.length,
        );
    }

    clickToHidePopup() {
        this.interactions.clickToHidePopup();
    }

    hidePopup() {
        this.interactions.hidePopup();
    }

    onInfoBoxClicked() {
        this.interactions.onInfoBoxClicked();
    }

    /**
     * @param {number} timestamp
     */
    onTimeSliderChange(timestamp) {
        if (this.webglTrailLayer) {
            this.trail.updateWebGLLayerTime(this.webglTrailLayer, timestamp);
        }
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @returns {boolean}
     */
    _shouldUseWebGLTrail(layerConfig, data) {
        if (!this.props.archInfo?.webglTrail) {
            return false;
        }

        if (!data || data.length === 0) {
            return false;
        }

        const timestampsField =
            this.props.archInfo.trailTimestampsField || "trail_timestamps";

        return !!savedValue(data[0], timestampsField);
    }

    renderRasterLayers() {
        debugLog("renderRasterLayers() - Starting");

        if (!this.map) {
            debugLog("Required objects not available");
            return;
        }

        const rasters = this.props.model.layers.rasters;
        if (!rasters || rasters.length === 0) {
            debugLog("No raster layers configured for scope:", this.layerScope);
            return;
        }

        const baseMapsLayer = this.map
            .getLayers()
            .getArray()
            .find((layer) => layer.get("title") === "Base maps");

        if (!baseMapsLayer) {
            debugLog("Base maps layer not found");
            return;
        }

        const newBackgroundLayers = this.rasters.createBackgroundLayers(rasters);

        baseMapsLayer.getLayers().clear();
        newBackgroundLayers.forEach((layer) => {
            if (layer) {
                baseMapsLayer.getLayers().push(layer);
            }
        });

        debugLog("Raster layers updated");
    }

    /** @param {boolean} [rebuild=false] */
    onRasterLayerChanged(rebuild = false) {
        const baseMaps = this.map
            ?.getLayers()
            .getArray()
            .find((layer) => layer.get("title") === "Base maps");
        const rasters = this.props.model.layers.rasters;
        const byId = new Map(rasters.map((raster) => [raster.id, raster]));
        let matched = 0;
        for (const layer of baseMaps?.getLayers().getArray() || []) {
            const config = byId.get(layer.get("layerId"));
            if (config) {
                layer.setVisible(config.isVisible === true);
                matched++;
            }
        }
        if (rebuild || matched !== rasters.length) {
            this.renderRasterLayers();
        }
    }

    /**
     * @param {number} layerResId
     * @returns {Object|undefined}
     */
    _olLayerFor(layerResId) {
        return (this.vectorLayersResult || []).find(
            (layer) => layer.get("layerId") === layerResId,
        );
    }

    /**
     * @param {number} layerResId
     * @param {boolean} visible
     */
    setLayerVisibility(layerResId, visible) {
        this._olLayerFor(layerResId)?.setVisible(visible);
        this.styling?.toggleLegend(layerResId, visible);
        if (visible) {
            this.props.model.showLayer(layerResId);
        }
    }

    /**
     * @param {number} layerResId
     * @param {number} sequence
     */
    setLayerOrder(layerResId, sequence) {
        this._olLayerFor(layerResId)?.setZIndex(sequence);
    }

    async onVectorLayerChanged() {
        await this.props.model.reloadLayerConfigurations();
    }

    renderVectorLayers() {
        debugLog("🟢 [RENDERER] ============ renderVectorLayers() START ============");
        const endVectors = log.perf("renderVectorLayers");

        if (!this.map) {
            debugLog("🟢 [RENDERER] Map not initialized yet, creating it now...");
            this.renderMap();
        }

        debugLog("🟢 [RENDERER] OpenLayers and map ready, proceeding with render");

        const preparedLayers = this.props.model.root.data?.vectorLayers || [];
        debugLog("🟢 [RENDERER] Prepared layers from model:", {
            count: preparedLayers.length,
            layers: preparedLayers.map((l) => ({
                name: l.config?.name,
                hasData: !!l.data,
                dataCount: l.data?.length,
            })),
        });

        if (preparedLayers.length === 0) {
            const hasLayersConfigured = this.props.model.layers.vectors.length > 0;
            const modelHasLoaded = this.props.model.root.data !== undefined;

            debugLog("🟢 [RENDERER] No prepared layers - checking if warning needed", {
                hasLayersConfigured,
                modelHasLoaded,
            });

            if (modelHasLoaded) {
                this._removeExistingLayerGroups();
                this.vectorLayersResult = [];
            }
            if (modelHasLoaded && !hasLayersConfigured) {
                debugLog("🟢 [RENDERER] Showing missing layers warning");
                this.utils.showMissingLayersWarning();
            } else {
                debugLog(
                    "🟢 [RENDERER] Skipping warning (model still loading or layers configured)",
                );
            }
            return;
        }

        debugLog("🟢 [RENDERER] Starting layer rendering process...");

        this.webglTrailLayer = null;
        this.state.showTimeSlider = false;

        debugLog("🟢 [RENDERER] Removing existing layer groups from map");
        this._removeExistingLayerGroups();

        debugLog("🟢 [RENDERER] Creating OpenLayers layers from prepared data");
        this.vectorLayersResult = [];
        for (const layerData of preparedLayers) {
            if (!layerData?.config) {
                console.error(
                    "[GeoengineRenderer] Invalid layer data (missing config):",
                    layerData,
                );
                continue;
            }

            const { config, data, styling, tiled } = layerData;
            debugLog(`🟢 [RENDERER] Creating layer: ${config.name}`, {
                dataCount: data?.length,
                hasStyling: !!styling,
            });

            try {
                let olLayer;

                if (this._shouldUseWebGLTrail(config, data)) {
                    debugLog(
                        `🟢 [RENDERER] Using WebGL for trail layer: ${config.name}`,
                    );
                    const webglResult = this.trail.createWebGLTrailLayer(config, data);
                    if (webglResult) {
                        olLayer = webglResult.layer;
                        this.webglTrailLayer = webglResult.layer;
                        this.state.showTimeSlider = true;
                        this.state.timeSliderKey++;
                        this.state.timeSliderMin = webglResult.minTimestamp;
                        this.state.timeSliderMax = webglResult.maxTimestamp;
                        this.state.trailColor =
                            webglResult.trailColor || DEFAULT_TRAIL_COLOR;
                        debugLog(
                            `🟢 [RENDERER] WebGL layer created, time range: ${webglResult.minTimestamp} - ${webglResult.maxTimestamp}`,
                        );
                    }
                } else {
                    olLayer = this.layers.createVectorLayer(
                        config,
                        data,
                        styling,
                        tiled,
                    );
                }

                if (olLayer) {
                    this.vectorLayersResult.push(olLayer);
                    debugLog(
                        `🟢 [RENDERER] Layer created successfully: ${config.name}`,
                    );
                } else {
                    console.warn(
                        `[GeoengineRenderer] Layer creation returned null: ${config.name}`,
                    );
                }
            } catch (error) {
                console.error(
                    `[GeoengineRenderer] Error creating layer ${config?.name || "unknown"}:`,
                    error,
                );
            }
        }

        debugLog("🟢 [RENDERER] All layers created", {
            totalLayers: this.vectorLayersResult.length,
        });

        const vectors = this.props.model.layers.vectors;
        const byResId = new Map(vectors.map((config) => [config.resId, config]));

        this.styling.pruneLegends(this.vectorLayersResult.map((l) => l.get("layerId")));
        for (const vlayer of this.vectorLayersResult) {
            const layerConfig = byResId.get(vlayer.get("layerId"));
            if (layerConfig) {
                vlayer.setVisible(layerConfig.isVisible);
            }
        }

        debugLog("🟢 [RENDERER] Creating and adding layer groups to map");
        this._createAndAddLayerGroups(this.vectorLayersResult);
        debugLog("🟢 [RENDERER] Layer groups added to map");

        this.interactions.refreshForLayers();

        debugLog("🟢 [RENDERER] Updating map zoom");
        this.updateZoom();
        debugLog("🟢 [RENDERER] Zoom updated");

        debugLog(
            "🟢 [RENDERER] ============ renderVectorLayers() COMPLETE ============",
        );
        endVectors({ layers: this.vectorLayersResult?.length });
    }

    _removeExistingLayerGroups() {
        const layersToRemove = [];
        this.map.getLayers().forEach((layer) => {
            if (!layer) {
                return;
            }

            const title = layer.get("title");
            if (title === "Overlays" || title === "Data Layers") {
                layersToRemove.push(layer);
            }
        });

        for (const group of layersToRemove) {
            this.map.removeLayer(group);
            for (const layer of group.getLayers().getArray()) {
                layer.dispose();
            }
        }
    }

    /**
     * @param {Array<ol.layer.Vector>} vectorLayers
     */
    _createAndAddLayerGroups(vectorLayers) {
        this.vectorLayersGroup = new ol.layer.Group({
            title: "Data Layers",
            layers: vectorLayers,
        });

        this.map.addLayer(this.vectorLayersGroup);

        debugLog("Layer group created and added to map", {
            layerCount: vectorLayers.length,
        });
    }

    updateZoom() {
        if (this.isFit) {
            return;
        }
        const hasFeatures = (this.vectorLayersResult || []).some(
            (layer) =>
                layer.get("dataExtent") ||
                layer.getSource()?.getFeatures?.().length > 0,
        );
        if (!hasFeatures) {
            if (!this.isFitToConfiguredExtent) {
                debugLog("updateZoom() - No features; framing the configured extent");
                this.isFitToConfiguredExtent = this.utils.fitConfiguredExtent();
            }
            return;
        }
        this.utils.getOriginalZoom();
        const savedZoom = this.utils.getStoredZoom();
        if (savedZoom !== null) {
            this.map.getView().setZoom(savedZoom);
        }
        this.isFit = true;
    }

    cleanupResources() {
        debugLog("=== Starting cleanup ===");

        const safeDispose = (target) => {
            try {
                target?.dispose?.();
            } catch (error) {
                debugLog("dispose() failed, continuing cleanup:", error);
            }
        };

        try {
            try {
                this.spatialFilter?.stop();
                this.interactions?.teardown();
                this.mapTools?.teardown();
            } catch (error) {
                debugLog("mapTools teardown failed, continuing cleanup:", error);
            }

            if (this.trails) {
                debugLog("Cleaning up trails system");

                if (this.map) {
                    for (const [, trailLayer] of this.trails.trailLayers.entries()) {
                        this.map.removeLayer(trailLayer);
                        const source = trailLayer.getSource();
                        if (source) {
                            source.clear();
                        }
                    }
                }

                this.trails.cleanup();
            }

            if (this.vectorLayersGroup && this.map) {
                debugLog("Removing vector layers group from map");
                this.map.removeLayer(this.vectorLayersGroup);
                this.vectorLayersGroup.getLayers().clear();
                this.vectorLayersGroup = null;
            }

            if (this.vectorLayersResult) {
                debugLog("Clearing vector layers");
                for (const layer of this.vectorLayersResult) {
                    const source = layer.getSource();
                    if (source) {
                        source.clear();
                    }
                    if (this.map) {
                        this.map.removeLayer(layer);
                    }
                    safeDispose(layer);
                }
                this.vectorLayersResult = [];
            }

            if (this.map) {
                debugLog("Removing map interactions and event listeners");

                if (this.utils) {
                    this.utils.removeMoveEndListener();
                }

                if (this.selectClick) {
                    this.map.removeInteraction(this.selectClick);
                    this.selectClick = null;
                }

                if (this.selectPointerMove) {
                    this.map.removeInteraction(this.selectPointerMove);
                    this.selectPointerMove = null;
                }

                const interactions = this.map.getInteractions().getArray().slice();
                for (const interaction of interactions) {
                    this.map.removeInteraction(interaction);
                }
            }

            if (this.map) {
                debugLog("Disposing OpenLayers map");

                if (this.overlay) {
                    this.map.removeOverlay(this.overlay);
                    this.overlay = null;
                }

                this.map.setTarget(null);
                safeDispose(this.map);
                this.map = null;
            }

            this.format = null;
            this.layers = null;
            this.rasters = null;
            this.trail = null;
            this.styling = null;
            this.interactions = null;
            this.utils = null;
            this.trails = null;
            this.webglTrailLayer = null;

            debugLog("=== Cleanup complete ===");
        } catch (error) {
            console.error("[GeoengineRenderer] Error during cleanup:", error);
        }
    }
}
