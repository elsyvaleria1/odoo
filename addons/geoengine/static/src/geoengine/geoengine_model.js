/** @odoo-module native */
import { markRaw, toRaw } from "@odoo/owl";
import { Domain } from "@web/core/domain";
import { evaluateExpr } from "@web/core/py_js/py";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { RelationalModel } from "@web/model/relational_model";

import { makeGeoLogger } from "../geo_debug.js";
import { loadGeoLibs, registerProjections } from "../lib/geo_libs.js";
import { nameActiveIds, withActiveIds } from "./active_ids.js";
import { LayerClassifier } from "./layer_classifier.js";
import { savedValues } from "./record_values.js";
import { DEFAULT_WEBGL_THRESHOLD } from "./renderer/render_strategies.js";

const debugLog = makeGeoLogger("GeoengineModel");
const log = debugLog.log;

const LAYER_DATA_FETCH_LIMIT = 10000;
const DENSE_TILE_WARNING = () =>
    _t(
        "Part of this layer holds too many records to draw in time. Zoom in, or narrow the search.",
    );
const DEFAULT_PROJECTION = "EPSG:3857";

/**
 * @param {number} recordCount
 * @returns {string|null}
 */
export function layerTruncationWarning(recordCount) {
    if (recordCount < LAYER_DATA_FETCH_LIMIT) {
        return null;
    }
    return _t(
        "Showing the first %(limit)s features. Narrow this layer's filter to see them all.",
        { limit: LAYER_DATA_FETCH_LIMIT },
    );
}

/**
 * @param {string|false} raw
 * @returns {number[]|null}
 */
export function parseExtent(raw) {
    if (!raw || typeof raw !== "string") {
        return null;
    }
    const parts = raw.split(",").map((p) => Number(p.trim()));
    if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) {
        return null;
    }
    const [minX, minY, maxX, maxY] = parts;
    return minX < maxX && minY < maxY ? parts : null;
}

export class DomainHasher {
    /**
     * @param {Array} domain
     * @returns {string}
     */
    static hash(domain) {
        if (!domain || domain.length === 0) {
            return "[]";
        }

        try {
            const domainObj = new Domain(domain);
            return domainObj.toString();
        } catch (error) {
            console.warn(
                "[DomainHasher] Failed to normalize domain, using fallback:",
                error,
            );
            return JSON.stringify(domain);
        }
    }
}

/**
 * The key the renderer stores its per-view zoom under.
 *
 * @param {string} resModel
 * @param {number|null} viewId
 * @returns {string}
 */
export function layerScopeKey(resModel, viewId) {
    return `${resModel}#${viewId || "default"}`;
}

export class GeoengineModel extends RelationalModel {
    /**
     * @param {Object} params
     * @param {Object} services
     */
    setup(params, services) {
        super.setup(params, services);
        debugLog("Initializing GeoengineModel");

        this.view = services.view;
        this.layers = { vectors: [], rasters: [] };
        this.geoViewId = params.geoViewId || null;
        this._geoDataTicket = 0;
        this.layerScope = layerScopeKey(
            params.resModel || this.config?.resModel,
            this.geoViewId,
        );

        this.classifier = new LayerClassifier(this.orm);
        this.subscribeLifecycle("onRootLoaded", (root) => this._prepareGeoData(root));

        this.relatedModels = new Map();
        this.loadingViews = new Map();

        this.inflightFetches = new Map();

        this.layerStatus = new Map();
        this._denseZooms = new Map();
        this.layerDomainOverrides = new Map();
        this.deferredLayers = new Set();

        this._librariesLoaded = loadGeoLibs();
        this._layerConfigsLoaded = this._loadLayerConfigurations(params);

        debugLog("GeoengineModel initialized", { params });
    }

    /**
     * @param {Object} params
     * @returns {Promise<void>}
     */
    async _loadLayerConfigurations(params) {
        const resModel = params.resModel || this.config?.resModel;
        debugLog("🟢 [MODEL SETUP] Loading layer configurations for model:", resModel);

        if (!resModel) {
            debugLog(
                "🟢 [MODEL SETUP] No resModel available, skipping layer configuration load",
            );
            this._setLayers([], []);
            this._layerValidation = {};
            return;
        }

        try {
            const result = await this.orm.call(resModel, "get_layers", [
                this.geoViewId,
            ]);
            await this._librariesLoaded;
            await registerProjections(result.projections);

            debugLog("🟢 [MODEL SETUP] Layer configurations received:", {
                backgrounds: result.backgrounds?.length || 0,
                actives: result.actives?.length || 0,
                hasValidation: !!result.validation,
            });

            this._layerValidation = result.validation || {};

            this._renderEngineConfig = {
                render_engine: result.render_engine || "auto",
                webgl_threshold: result.webgl_threshold || DEFAULT_WEBGL_THRESHOLD,
            };

            this._mapConfig = {
                projection: result.projection || DEFAULT_PROJECTION,
                defaultExtent: parseExtent(result.default_map_extent),
                restrictedExtent: parseExtent(result.restricted_extent),
                defaultZoom: result.default_map_zoom || null,
                controls: result.controls || {},
            };

            this._setLayers(result.actives || [], result.backgrounds || []);
            debugLog("🟢 [MODEL SETUP] Layer configurations loaded successfully", {
                rasters: this.layers.rasters.length,
                vectors: this.layers.vectors.length,
            });
        } catch (error) {
            console.error(
                "[GeoengineModel] Failed to load layer configurations:",
                error,
            );

            this._layerValidation = {
                errors: [`Failed to load layer configurations: ${error.message}`],
            };
            this._setLayers([], []);
        }
    }

    /**
     * The layer configuration is state of this model: the renderer and the
     * panel read it through the reactive model they receive as a prop, so a
     * visibility toggle or a reorder in one is seen by the other with no
     * event bus in between. A vector starts visible when it is active on
     * startup; the first non-overlay raster is the visible base map.
     *
     * @param {Object[]} vectors
     * @param {Object[]} rasters
     */
    _setLayers(vectors, rasters) {
        let baseShown = false;
        this.layers.vectors = vectors.map((vector) => ({
            ...vector,
            isVisible: vector.active_on_startup || false,
        }));
        this.layers.rasters = rasters.map((raster) => {
            const isVisible = !raster.overlay && !baseShown;
            baseShown ||= isVisible;
            return { ...raster, isVisible };
        });
    }

    /**
     * @returns {Object}
     */
    getLayerValidation() {
        return this._layerValidation || {};
    }

    /**
     * @returns {Object}
     */
    getRenderEngineConfig() {
        return (
            this._renderEngineConfig || {
                render_engine: "auto",
                webgl_threshold: DEFAULT_WEBGL_THRESHOLD,
            }
        );
    }

    /**
     * @returns {Object}
     */
    getMapConfig() {
        return (
            this._mapConfig || {
                projection: DEFAULT_PROJECTION,
                defaultExtent: null,
                restrictedExtent: null,
                defaultZoom: null,
                controls: {},
            }
        );
    }

    /**
     * @param {number} layerId
     * @param {Object} status
     * @param {boolean} [status.loading=false]
     * @param {string|null} [status.error=null]
     * @param {string|null} [status.warning=null]
     */
    setLayerStatus(layerId, { loading = false, error = null, warning = null }) {
        this.layerStatus.set(layerId, { loading, error, warning });
    }

    /**
     * @param {number} layerId
     * @returns {Object|null}
     */
    getLayerStatus(layerId) {
        return this.layerStatus.get(layerId) || null;
    }

    /**
     * @param {Object} params
     * @returns {Promise<void>}
     */
    async load(params) {
        const endLoad = log.perf("load");
        log.pipeline("load", () => ({ resModel: this.config.resModel, params }));
        await Promise.all([this._librariesLoaded, this._layerConfigsLoaded]);
        await super.load(params);
        endLoad({
            vectors: this.layers?.vectors?.length,
            rasters: this.layers?.rasters?.length,
        });
    }

    /**
     * Re-reads the layer configuration from the server and redraws. The
     * server is the only place that resolves a layer's field names, model and
     * projected extents, so a saved edit is not patched client-side. The
     * user's visibility toggles survive the reload.
     *
     * @returns {Promise<void>}
     */
    async reloadLayerConfigurations() {
        log.lifecycle("reloadLayerConfigurations", () => ({
            vectors: this.layers.vectors.length,
        }));
        const visible = new Map(
            this.layers.vectors.map((layer) => [layer.resId, layer.isVisible]),
        );
        this._layerConfigsLoaded = this._loadLayerConfigurations({
            resModel: this.config.resModel,
        });
        await this._layerConfigsLoaded;
        for (const layer of this.layers.vectors) {
            if (visible.has(layer.resId)) {
                layer.isVisible = visible.get(layer.resId);
            }
            if (this.layerDomainOverrides.has(layer.resId)) {
                layer.model_domain = this.layerDomainOverrides.get(layer.resId);
            }
        }
        await this._prepareGeoData(this.root);
    }

    /**
     * A hidden layer is not read until it is first shown.
     *
     * @param {number} layerId
     * @returns {Promise<void>}
     */
    async showLayer(layerId) {
        if (this.deferredLayers.has(layerId)) {
            await this._prepareGeoData(this.root);
        }
    }

    /**
     * Filters a layer for this session only, for a user who cannot change the
     * layer itself; it survives configuration reloads until the map closes.
     *
     * @param {number} layerId
     * @param {string} domain
     * @returns {Promise<void>}
     */
    async overrideLayerDomain(layerId, domain) {
        this.layerDomainOverrides.set(layerId, domain);
        const layer = this.layers.vectors.find((vector) => vector.resId === layerId);
        if (layer) {
            layer.model_domain = domain;
        }
        await this._prepareGeoData(this.root);
    }

    /**
     * @param {Object} root
     * @returns {Promise<void>}
     */
    async _prepareGeoData(root) {
        const ticket = ++this._geoDataTicket;
        const deferred = new Set(
            this.layers.vectors
                .filter((layer) => !layer.isVisible)
                .map((layer) => layer.resId),
        );
        const vectorLayers = await this._prepareVectorLayers(root, deferred);
        if (ticket !== this._geoDataTicket || toRaw(root) !== toRaw(this.root)) {
            debugLog(
                "_prepareGeoData() - a newer load superseded this one, dropping it",
            );
            return;
        }
        this.deferredLayers = deferred;
        root.data = {
            vectorLayers: markRaw(vectorLayers),
            rasterLayers: this._prepareRasterLayers(),
        };
    }

    /**
     * @param {Object} root
     * @returns {Promise<Array>}
     */
    async _prepareVectorLayers(root = this.root, deferred = new Set()) {
        const vectors = this.layers.vectors;

        debugLog("🔵 [MODEL] _prepareVectorLayers() - START", {
            resModel: this.config.resModel,
            layerCount: vectors.length,
        });

        if (!vectors || vectors.length === 0) {
            debugLog("🔵 [MODEL] _prepareVectorLayers() - No vector layers to prepare");
            return [];
        }

        const layersByModel = new Map();
        const layerIndices = new Map();

        for (let i = 0; i < vectors.length; i++) {
            const config = vectors[i];
            const modelKey = config.model || root.resModel;

            if (!layersByModel.has(modelKey)) {
                layersByModel.set(modelKey, []);
            }
            layersByModel.get(modelKey).push(config);

            layerIndices.set(config, i);
        }

        debugLog("🔵 [MODEL] _prepareVectorLayers() - Grouped layers by model:", {
            modelCount: layersByModel.size,
            groups: Array.from(layersByModel.entries()).map(([model, configs]) => ({
                model,
                layerCount: configs.length,
            })),
        });

        debugLog(
            "🔵 [MODEL] _prepareVectorLayers() - PHASE 1: Loading all views in parallel",
        );
        const viewLoadPromises = Array.from(layersByModel.keys())
            .filter((modelKey) => modelKey !== root.resModel)
            .map(async (modelKey) => {
                debugLog(
                    `🔵 [MODEL] _prepareVectorLayers() - Loading view for model: ${modelKey}`,
                );
                try {
                    await this.loadView(modelKey);
                    return { modelKey, success: true };
                } catch (error) {
                    debugLog(`Cannot load a geoengine view for ${modelKey}`, error);
                    return { modelKey, success: false, error };
                }
            });

        const viewResults = await Promise.all(viewLoadPromises);
        const failedModels = new Set(
            viewResults.filter((r) => !r.success).map((r) => r.modelKey),
        );

        for (const { modelKey } of viewResults.filter((r) => !r.success)) {
            for (const config of layersByModel.get(modelKey) || []) {
                this.setLayerStatus(config.resId, {
                    error: _t(
                        "%(model)s has no geoengine view, so this layer cannot be drawn.",
                        { model: modelKey },
                    ),
                });
            }
        }

        debugLog("🔵 [MODEL] _prepareVectorLayers() - PHASE 1 complete:", {
            successCount: viewResults.filter((r) => r.success).length,
            failureCount: failedModels.size,
            failedModels: Array.from(failedModels),
        });

        debugLog(
            "🔵 [MODEL] _prepareVectorLayers() - PHASE 2: Fetching data for all layers in parallel",
        );
        const allConfigs = [];
        for (const [modelKey, configs] of layersByModel) {
            if (failedModels.has(modelKey)) {
                debugLog(
                    `🔵 [MODEL] _prepareVectorLayers() - Skipping layers for failed model: ${modelKey}`,
                );
                continue;
            }
            allConfigs.push(...configs);
        }

        const dataPromises = allConfigs.map(async (config) => {
            if (deferred.has(config.resId)) {
                return { config, data: [], population: null, error: null };
            }
            try {
                debugLog(
                    `🔵 [MODEL] _prepareVectorLayers() - Fetching data for layer: ${config.name}`,
                );

                this.setLayerStatus(config.resId, { loading: true });

                const tiled = await this._tiledLayer(config, root);
                this._denseZooms.delete(config.resId);
                if (tiled) {
                    const population = await this._loadPopulation(config, root);
                    this.setLayerStatus(config.resId, {});
                    return { config, data: [], population, tiled, error: null };
                }

                const { records: data, complete } = await this.getLayerData(
                    config,
                    this._getLayerFields(config),
                    root,
                );
                const population = complete
                    ? null
                    : await this._loadPopulation(config, root);

                debugLog(
                    `🔵 [MODEL] _prepareVectorLayers() - Data fetched for ${config.name}:`,
                    {
                        recordCount: data.length,
                        complete,
                        population: Boolean(population),
                    },
                );

                this.setLayerStatus(config.resId, {
                    warning: layerTruncationWarning(data.length),
                });

                return { config, data, population, error: null };
            } catch (error) {
                console.error(
                    `[GeoengineModel] Error fetching data for layer ${config.name}:`,
                    error,
                );

                this.setLayerStatus(config.resId, {
                    error: error.message || "Unknown error",
                });

                return { config, data: [], population: null, error };
            }
        });

        const results = await Promise.all(dataPromises);

        debugLog(`🔵 [MODEL] _prepareVectorLayers() - PHASE 2 complete:`, {
            successCount: results.filter((r) => !r.error).length,
            errorCount: results.filter((r) => r.error).length,
        });

        debugLog(
            "🔵 [MODEL] _prepareVectorLayers() - PHASE 3: Classifying and preparing layers",
        );
        const layersWithIndices = [];

        for (const { config, data, population, tiled, error } of results) {
            if (error) {
                continue;
            }

            let styling = null;
            if (
                config.classification &&
                config.attribute_field_name &&
                (data.length > 0 || (tiled && population))
            ) {
                debugLog(
                    `🔵 [MODEL] _prepareVectorLayers() - Classifying data for ${config.name}`,
                    {
                        geo_repr: config.geo_repr,
                        classification: config.classification,
                    },
                );

                try {
                    styling = this.classifier.classify(config, data, population);
                    debugLog(
                        `🔵 [MODEL] _prepareVectorLayers() - Styling created for ${config.name}`,
                    );
                } catch (error) {
                    console.error(
                        `[GeoengineModel] Error classifying layer ${config.name}:`,
                        error,
                    );

                    this.setLayerStatus(config.resId, {
                        warning: _t("Classification failed: %s", error.message),
                    });
                }
            }

            layersWithIndices.push({
                layer: {
                    config,
                    data,
                    styling,
                    tiled: tiled || null,
                },
                originalIndex: layerIndices.get(config),
            });

            debugLog(
                `🔵 [MODEL] _prepareVectorLayers() - Layer prepared: ${config.name}`,
                {
                    dataCount: data.length,
                    hasStyling: !!styling,
                    isVisible: config.isVisible,
                    originalIndex: layerIndices.get(config),
                },
            );
        }

        layersWithIndices.sort((a, b) => a.originalIndex - b.originalIndex);
        const layers = layersWithIndices.map((item) => item.layer);

        debugLog("🔵 [MODEL] _prepareVectorLayers() - COMPLETE", {
            totalLayers: layers.length,
            orderPreserved: true,
        });

        return layers;
    }

    /**
     * The rows a layer draws, and whether they are its whole population: the
     * view's own records when they carry every styled field, else a fetch with
     * the layer's effective domain.
     *
     * @param {Object} layerConfig
     * @param {string[]} fieldsToRead
     * @returns {Promise<{records: Object[], complete: boolean}>}
     */
    async getLayerData(layerConfig, fieldsToRead, root = this.root) {
        debugLog("getLayerData() - START", {
            layer: layerConfig.name,
            model: layerConfig.model,
            fields: fieldsToRead,
        });

        const layerDomain = this.evalDomain(layerConfig, root);
        if (layerConfig.model === root.resModel && layerDomain.length === 0) {
            const records = root.records || [];
            const complete = records.length === root.count;
            if (!this._missingLayerFields(layerConfig, root).length) {
                debugLog(
                    "getLayerData() - Using view's data (same model, no layer domain)",
                );
                return { records, complete };
            }
            debugLog("getLayerData() - reading the fields the view's records lack");
            const pageIds = records.map((record) => record.resId);
            return {
                records: await this._doFetchLayerData(
                    layerConfig.model,
                    [["id", "in", pageIds]],
                    fieldsToRead,
                ),
                complete,
            };
        }

        const domain = this._effectiveLayerDomain(layerConfig, layerDomain, root);
        const cacheKey = `${layerConfig.model}_${layerConfig.resId}_${DomainHasher.hash(domain)}`;
        debugLog("getLayerData() - fetching", {
            layerDomain,
            effective: domain,
            cacheKey,
        });

        let fetch = this.inflightFetches.get(cacheKey);
        if (!fetch) {
            fetch = this._doFetchLayerData(layerConfig.model, domain, fieldsToRead);
            this.inflightFetches.set(cacheKey, fetch);
            fetch.finally(() => this.inflightFetches.delete(cacheKey)).catch(() => {});
        }
        const records = await fetch;
        return { records, complete: records.length < LAYER_DATA_FETCH_LIMIT };
    }

    /**
     * A layer whose features would be truncated is drawn as vector tiles of
     * its whole population instead: the view's own layer when the page holds
     * fewer records than the search matched, any other when its population
     * exceeds the fetch limit. Tiles are cut in Web Mercator, so another
     * projection is not tiled; a heatmap reads its view's cells instead of
     * tiles (ViewportHeatStrategy).
     *
     * @param {Object} layerConfig
     * @returns {Promise<{domain: Array, extent: number[]|null}|null>}
     */
    async _tiledLayer(layerConfig, root = this.root) {
        if (this.getMapConfig().projection !== DEFAULT_PROJECTION || root.isGrouped) {
            return null;
        }
        const layerDomain = this.evalDomain(layerConfig, root);
        const resModel = layerConfig.model || root.resModel;
        const domain = this._effectiveLayerDomain(layerConfig, layerDomain, root);
        let truncated;
        if (resModel === root.resModel && layerDomain.length === 0) {
            truncated = (root.records?.length ?? 0) < (root.count ?? 0);
        } else {
            const count = await this.orm.searchCount(resModel, domain, {
                limit: LAYER_DATA_FETCH_LIMIT + 1,
            });
            truncated = count > LAYER_DATA_FETCH_LIMIT;
        }
        if (!truncated) {
            return null;
        }
        const extent = await this.orm.silent
            .call("geoengine.vector.layer", "get_tile_extent", [
                [layerConfig.resId],
                domain,
            ])
            .catch((error) => {
                debugLog("No extent for a tiled layer:", layerConfig.name, error);
                return null;
            });
        log.pipeline("tiled layer", () => ({
            layer: layerConfig.name,
            domain,
            extent,
        }));
        return { domain, extent };
    }

    /**
     * Whether the map draws every record the search matched, not the page:
     * the view's own layer is tiled.
     *
     * @returns {boolean}
     */
    drawsEveryMatch() {
        const resModel = this.root.resModel;
        return (this.root.data?.vectorLayers || []).some(
            ({ config, tiled }) => tiled && (config.model || resModel) === resModel,
        );
    }

    /**
     * Whether a tiled layer's last tile could not be drawn in time: the layer
     * warns while the zoom it shows holds a refused tile, and stops once the
     * tiles of another zoom all render.
     *
     * @param {number} layerId
     * @param {number} zoom
     * @param {boolean} dense
     */
    reportTileDensity(layerId, zoom, dense) {
        const denseZooms = this._denseZooms.get(layerId) || new Set();
        this._denseZooms.set(layerId, denseZooms);
        if (dense) {
            denseZooms.add(zoom);
        }
        const warning = denseZooms.has(zoom) ? DENSE_TILE_WARNING() : null;
        const status = this.getLayerStatus(layerId);
        const ownWarning = !status?.warning || status.warning === DENSE_TILE_WARNING();
        if (ownWarning && (status?.warning ?? null) !== warning) {
            this.setLayerStatus(layerId, { ...status, warning });
        }
    }

    /**
     * The records a tiled layer counted in one fine-grid cell.
     *
     * @param {number} layerId
     * @param {string} cell
     * @returns {Promise<{records: {id: number, display_name: string}[], more: boolean}>}
     */
    async readCellRecords(layerId, cell) {
        const layer = (this.root.data?.vectorLayers || []).find(
            ({ config }) => config.resId === layerId,
        );
        if (!layer?.tiled) {
            return { records: [], more: false };
        }
        return this.orm.call("geoengine.vector.layer", "get_cell_records", [
            [layerId],
            cell,
            layer.tiled.domain,
        ]);
    }

    /**
     * The row a tiled feature's popup shows: the fields the view's records
     * load, or the layer model's info box fields.
     *
     * @param {string} resModel
     * @param {number} resId
     * @returns {Promise<Object|null>}
     */
    async readTiledRecord(resModel, resId) {
        const names =
            resModel === this.root.resModel
                ? Object.keys(this.root.activeFields || {})
                : Object.keys(
                      this.relatedModels?.get(resModel)?.archInfo?.fieldNodes || {},
                  );
        const [row] = await this.orm.searchRead(
            resModel,
            [["id", "=", resId]],
            [...new Set(["id", ...names])],
        );
        return row || null;
    }

    /**
     * @param {Object} layerConfig
     * @returns {Promise<Object|null>}
     */
    async _loadPopulation(layerConfig, root = this.root) {
        return this.classifier.loadPopulation(
            layerConfig,
            this._effectiveLayerDomain(
                layerConfig,
                this.evalDomain(layerConfig, root),
                root,
            ),
        );
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} layerDomain
     * @returns {Array}
     */
    _effectiveLayerDomain(layerConfig, layerDomain, root = this.root) {
        if (
            layerConfig.model === root.resModel &&
            root.domain &&
            root.domain.length > 0
        ) {
            return [...root.domain, ...layerDomain];
        }
        return layerDomain;
    }

    /**
     * @param {Object} layerConfig
     * @returns {string[]}
     */
    _missingLayerFields(layerConfig, root = this.root) {
        const sample = (root.records || [])[0];
        if (!sample) {
            return [];
        }
        const available = savedValues(sample);
        return this._getLayerFields(layerConfig).filter(
            (name) => name && !(name in available),
        );
    }

    async _doFetchLayerData(model, domain, fieldsToRead) {
        const endFetch = log.perf(`fetchLayerData ${model}`);
        const records = await this.orm.searchRead(model, domain, fieldsToRead, {
            limit: LAYER_DATA_FETCH_LIMIT,
        });
        endFetch({ model, fields: fieldsToRead.length, records: records.length });
        return records;
    }

    /**
     * @param {string} model
     * @param {string} viewType
     * @returns {Promise<void>}
     * @throws {Error}
     */
    async loadView(model) {
        if (this.relatedModels.has(model)) {
            return;
        }
        const existingPromise = this.loadingViews.get(model);
        if (existingPromise) {
            await existingPromise;
            return;
        }
        const loadingPromise = this._doLoadView(model);
        this.loadingViews.set(model, loadingPromise);
        try {
            await loadingPromise;
        } finally {
            this.loadingViews.delete(model);
        }
    }

    async _doLoadView(model) {
        const { relatedModels, views } = await this.view.loadViews({
            resModel: model,
            views: [[false, "geoengine"]],
        });
        const { ArchParser } = registry.category("views").get("geoengine");
        const archInfo = new ArchParser().parse(
            views.geoengine.ir,
            relatedModels,
            model,
        );
        this.relatedModels.set(model, {
            archInfo,
            fields: relatedModels[model].fields,
        });
        debugLog("View loaded successfully:", { model });
    }

    /**
     * @param {Object} layerConfig
     * @returns {Array}
     */
    evalDomain(layerConfig, root = this.root) {
        const activeIds = (root.records || []).map(
            (record) => record.resId || record.id,
        );
        if (
            layerConfig.domain !== undefined &&
            !this.layerDomainOverrides?.has(layerConfig.resId)
        ) {
            if (layerConfig.domain === null) {
                throw new Error(
                    _t(
                        "The layer's domain cannot be evaluated: %s",
                        layerConfig.model_domain,
                    ),
                );
            }
            return withActiveIds(layerConfig.domain, activeIds);
        }
        if (
            !layerConfig.model_domain ||
            layerConfig.model_domain === "[]" ||
            layerConfig.model_domain === ""
        ) {
            return [];
        }
        let domain;
        const domainExpr = nameActiveIds(layerConfig.model_domain);
        try {
            domain = evaluateExpr(domainExpr, {
                ...user.context,
                ACTIVE_IDS: activeIds,
            });
        } catch (error) {
            debugLog("Error evaluating domain:", {
                model_domain: layerConfig.model_domain,
                error,
            });
            throw new Error(
                _t("The layer's domain cannot be evaluated: %s", error.message),
                { cause: error },
            );
        }
        return domain;
    }

    /**
     * @param {Object} layerConfig
     * @returns {Array}
     */
    _getLayerFields(layerConfig) {
        const fields = ["id", layerConfig.geo_field_name];

        if (layerConfig.attribute_field_name) {
            fields.push(layerConfig.attribute_field_name);
        }

        if (layerConfig.color_field_name) {
            fields.push(layerConfig.color_field_name);
        }

        if (layerConfig.heatmap_weight_field_name) {
            fields.push(layerConfig.heatmap_weight_field_name);
        }

        const foreign = this.relatedModels?.get(layerConfig.model);
        for (const name of Object.keys(foreign?.archInfo?.fieldNodes || {})) {
            if (!fields.includes(name)) {
                fields.push(name);
            }
        }

        return fields;
    }

    /**
     * @returns {Array}
     */
    _prepareRasterLayers() {
        return this.layers.rasters;
    }
}

GeoengineModel.services = [...RelationalModel.services, "view"];
