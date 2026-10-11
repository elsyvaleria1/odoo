/** @odoo-module native */
import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";
import { parseExtent } from "../geoengine_model.js";

const debugLog = makeGeoLogger("RasterLayers");

export class RasterLayerBuilder {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
    }

    /**
     * @param {Array} backgrounds
     * @returns {Array<ol.layer.Tile>}
     */
    createBackgroundLayers(backgrounds) {
        if (!Array.isArray(backgrounds) || !backgrounds.length) {
            debugLog("No background layers configured, using default OSM", backgrounds);
            return [
                this._createRasterLayer({
                    name: "OpenStreetMap",
                    raster_type: "osm",
                    isVisible: true,
                }),
            ];
        }

        return backgrounds
            .map((background) => {
                debugLog(
                    `Creating layer for: ${background.name}, type: ${background.raster_type}, visible: ${background.isVisible}`,
                );
                const layer = this._createRasterLayer(background);
                layer?.set("layerId", background.id);
                layer?.setZIndex(background.overlay ? 1 : 0);
                return layer;
            })
            .filter(Boolean);
    }

    /**
     * @param {Object} background
     * @returns {ol.layer.Tile}
     */
    _fallbackOsmLayer(background) {
        return new ol.layer.Tile({
            title: background.name || "Fallback Map",
            visible: background.isVisible === true,
            type: "base",
            opacity: background.opacity ?? 1,
            source: new ol.source.OSM(),
        });
    }

    /**
     * @param {Object} background
     * @returns {ol.layer.Tile}
     */
    _createRasterLayer(background) {
        switch (background.raster_type) {
            case "osm": {
                return new ol.layer.Tile({
                    title: background.name,
                    visible: background.isVisible === true,
                    type: "base",
                    opacity: background.opacity,
                    source: new ol.source.OSM(),
                });
            }
            case "wmts": {
                try {
                    const { sourceOptions, tileGridOptions, layerOptions } =
                        this.createOptions(background);

                    if (!background.matrix_set) {
                        debugLog(
                            "WMTS layer missing required matrix_set, falling back to OSM:",
                            background.name,
                        );
                        return this._fallbackOsmLayer(background);
                    }

                    this.getUrl(background, sourceOptions);
                    if (background.format_suffix) {
                        const suffix = background.format_suffix.trim();
                        sourceOptions.format = suffix.includes("/")
                            ? suffix
                            : `image/${suffix.replace(/^\./, "")}`;
                    }
                    if (background.request_encoding) {
                        sourceOptions.requestEncoding = background.request_encoding;
                    }
                    if (background.projection) {
                        sourceOptions.projection = ol.proj.get(background.projection);
                        if (sourceOptions.projection) {
                            const projectionExtent =
                                sourceOptions.projection.getExtent();
                            tileGridOptions.origin =
                                ol.extent.getTopLeft(projectionExtent);
                        }
                    }
                    if (background.resolutions) {
                        tileGridOptions.resolutions = background.resolutions
                            .split(",")
                            .map(Number);
                        const nbRes = tileGridOptions.resolutions.length;
                        const matrixIds = new Array(nbRes);
                        for (let i = 0; i < nbRes; i++) {
                            matrixIds[i] = i;
                        }
                        tileGridOptions.matrixIds = matrixIds;
                    }
                    const extent = parseExtent(background.max_extent);
                    if (extent) {
                        layerOptions.extent = extent;
                        tileGridOptions.extent = extent;
                    }
                    if (background.params) {
                        sourceOptions.dimensions = JSON.parse(background.params);
                    }
                    sourceOptions.tileGrid = new ol.tilegrid.WMTS(tileGridOptions);
                    layerOptions.source = new ol.source.WMTS(sourceOptions);
                    return new ol.layer.Tile(layerOptions);
                } catch (error) {
                    debugLog("Error creating WMTS layer:", {
                        name: background.name,
                        error,
                    });
                    return this._fallbackOsmLayer(background);
                }
            }
            case "d_wms": {
                try {
                    const wmsSourceOptions = {
                        params: JSON.parse(background.params_wms),
                        serverType: background.server_type,
                    };
                    const urls = background.url.split(",");
                    if (urls.length > 1) {
                        wmsSourceOptions.urls = urls;
                    } else {
                        wmsSourceOptions.url = urls[0];
                    }

                    const wmsSource = new ol.source.TileWMS(wmsSourceOptions);

                    debugLog(
                        `WMS Layer "${background.name}" - URL: ${wmsSourceOptions.url}, Params: ${JSON.stringify(wmsSourceOptions.params)}`,
                    );

                    wmsSource.on("tileloaderror", (event) => {
                        debugLog(
                            `WMS tile load error for layer "${background.name}": URL: ${event.tile.src_}`,
                        );
                    });

                    return new ol.layer.Tile({
                        title: background.name,
                        visible: background.isVisible === true,
                        opacity: background.opacity,
                        source: wmsSource,
                    });
                } catch (error) {
                    debugLog("Error creating WMS layer:", {
                        name: background.name,
                        error,
                    });
                    return this._fallbackOsmLayer(background);
                }
            }
            case "i_wms": {
                try {
                    const imageSource = new ol.source.ImageWMS({
                        url: background.url,
                        params: JSON.parse(background.params_wms),
                        serverType: background.server_type,
                        attributions: background.attribution || undefined,
                    });
                    imageSource.on("imageloaderror", () => {
                        debugLog(`WMS image load error for "${background.name}"`);
                    });
                    return new ol.layer.Image({
                        title: background.name,
                        visible: background.isVisible === true,
                        opacity: background.opacity,
                        source: imageSource,
                    });
                } catch (error) {
                    debugLog("Error creating single-image WMS layer:", {
                        name: background.name,
                        error,
                    });
                    return this._fallbackOsmLayer(background);
                }
            }
            case "mvt": {
                try {
                    return new ol.layer.VectorTile({
                        title: background.name,
                        visible: background.isVisible === true,
                        opacity: background.opacity,
                        declutter: true,
                        source: new ol.source.VectorTile({
                            format: new ol.format.MVT(),
                            url: background.url,
                            maxZoom: background.max_zoom || 14,
                            attributions: background.attribution || undefined,
                        }),
                    });
                } catch (error) {
                    debugLog("Error creating vector tile layer:", {
                        name: background.name,
                        error,
                    });
                    return this._fallbackOsmLayer(background);
                }
            }
            case "xyz":
            case "google": {
                let url = background.url;
                if (!url && background.raster_type === "google") {
                    url = "https://mt{0-3}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}";
                }

                if (url) {
                    const sourceOptions = {
                        attributions: background.attribution || "",
                        maxZoom: background.max_zoom || 20,
                    };

                    if (url.includes("{0-3}") || url.includes("{1-4}")) {
                        const match = url.match(/\{(\d)-(\d)\}/);
                        if (match) {
                            const start = parseInt(match[1]);
                            const end = parseInt(match[2]);
                            const baseUrl = url.replace(/\{\d-\d\}/, "{subdomain}");
                            const urls = [];
                            for (let i = start; i <= end; i++) {
                                urls.push(baseUrl.replace("{subdomain}", i.toString()));
                            }
                            sourceOptions.urls = urls;
                        } else {
                            sourceOptions.url = url;
                        }
                    } else {
                        sourceOptions.url = url;
                    }

                    return new ol.layer.Tile({
                        title: background.name,
                        visible: background.isVisible === true,
                        type: "base",
                        opacity: background.opacity || 1,
                        source: new ol.source.XYZ(sourceOptions),
                    });
                }
                debugLog(
                    `Raster type '${background.raster_type}' for layer '${background.name}' has no URL. Falling back to OSM.`,
                );
                return this._fallbackOsmLayer(background);
            }
            default: {
                debugLog(
                    `Unknown or unconfigured raster_type '${background.raster_type}' for layer '${background.name}'. Falling back to OSM.`,
                );
                return this._fallbackOsmLayer(background);
            }
        }
    }

    /**
     * @param {Object} background
     * @param {Object} sourceOptions
     */
    getUrl(background, sourceOptions) {
        const wmtsUrls = background.url.split(",");
        if (wmtsUrls.length > 1) {
            sourceOptions.urls = wmtsUrls;
        } else {
            sourceOptions.url = wmtsUrls[0];
        }
    }

    /**
     * @param {Object} background
     * @returns {Object}
     */
    createOptions(background) {
        const tileGridOptions = {};
        const sourceOptions = {
            layer: background.wmts_layer,
            matrixSet: background.matrix_set,
            style: "default",
        };
        const layerOptions = {
            title: background.name,
            visible: background.isVisible === true,
            type: "base",
            opacity: background.opacity ?? 1,
        };
        return { sourceOptions, tileGridOptions, layerOptions };
    }
}
