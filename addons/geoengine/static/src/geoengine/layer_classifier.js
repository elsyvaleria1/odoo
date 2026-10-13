/** @odoo-module native */
import { LruCache } from "@web/core/utils/lru_cache";

import { makeGeoLogger } from "../geo_debug.js";
import { areGeoLibsLoaded, chroma, geostats } from "../lib/geo_libs.js";
import {
    classValue,
    DEFAULT_MIN_SIZE,
    INTERVAL,
    legendHtml,
    needsPopulationBounds,
    needsPopulationValues,
    QUANTILE,
    toRgbaString,
    UNIQUE,
    valueHash,
} from "./classification.js";
import { savedValue } from "./record_values.js";

const debugLog = makeGeoLogger("LayerClassifier");

const DEFAULT_BEGIN_COLOR = "#FFFFFF";
const DEFAULT_END_COLOR = "#000000";
const DEFAULT_MAX_SIZE = 15;
const DEFAULT_NUM_CLASSES = 5;
const LEGEND_MAX_ITEMS = 10;
const CACHE_SIZE = 50;

export class LayerClassifier {
    /**
     * @param {Object} orm
     */
    constructor(orm) {
        this.orm = orm;
        this.cache = new LruCache(CACHE_SIZE);
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} domain
     * @returns {Promise<{values?: Array, bounds?: Object}|null>}
     */
    async loadPopulation(layerConfig, domain) {
        const wantsBounds = needsPopulationBounds(layerConfig);
        const wantsValues = needsPopulationValues(layerConfig);
        if (!wantsBounds && !wantsValues) {
            return null;
        }
        const args = [[layerConfig.resId], domain];
        try {
            if (wantsValues) {
                const unique = layerConfig.classification === UNIQUE;
                const values = await this.orm.call(
                    "geoengine.vector.layer",
                    "get_class_values",
                    args,
                    unique ? { distinct: true } : {},
                );
                const classValues = (values || [])
                    .map(classValue)
                    .filter((value) => value !== null);
                if (classValues.length) {
                    return { values: classValues };
                }
                if (unique) {
                    return null;
                }
                const quantiles = await this.orm.call(
                    "geoengine.vector.layer",
                    "get_class_quantiles",
                    args,
                    { nb_class: layerConfig.nb_class || DEFAULT_NUM_CLASSES },
                );
                return quantiles?.length > 1 ? { quantiles } : null;
            }
            const bounds = await this.orm.call(
                "geoengine.vector.layer",
                "get_class_bounds",
                args,
            );
            return bounds && bounds.min !== undefined && bounds.max !== undefined
                ? { bounds }
                : null;
        } catch (error) {
            debugLog("loadPopulation() - falling back to the drawn subset:", {
                layer: layerConfig.name,
                error: error.message || error,
            });
            return null;
        }
    }

    /**
     * @param {Object} layerConfig
     * @param {Object[]} data
     * @param {Object|null} [population]
     * @returns {Object|null}
     */
    classify(layerConfig, data, population = null) {
        if (layerConfig.geo_repr === "proportion") {
            return this._proportional(layerConfig, data, population);
        }
        if (layerConfig.geo_repr === "colored") {
            return this._ranged(layerConfig, data, population);
        }
        return null;
    }

    /**
     * @param {Object|null} population
     * @returns {string}
     */
    _populationFingerprint(population) {
        if (population?.quantiles) {
            return `q${population.quantiles.join(",")}`;
        }
        if (population?.bounds) {
            return `${population.bounds.min}:${population.bounds.max}`;
        }
        if (population?.values) {
            let acc = population.values.length;
            for (const value of population.values) {
                acc = (acc * 31 + valueHash(value)) % 2147483647;
            }
            return `n${acc}`;
        }
        return "";
    }

    /**
     * @param {Object} layerConfig
     * @param {Object[]} data
     * @returns {Object|null}
     */
    _ranged(layerConfig, data, population) {
        const dataFingerprint = this._dataFingerprint(
            data,
            layerConfig.attribute_field_name,
        );
        const cacheKey = [
            layerConfig.resId,
            layerConfig.geo_repr,
            layerConfig.classification,
            layerConfig.attribute_field_name,
            layerConfig.nb_class,
            layerConfig.begin_color,
            layerConfig.end_color,
            layerConfig.layer_opacity,
            dataFingerprint,
            this._populationFingerprint(population),
        ].join("_");

        if (this.cache.has(cacheKey)) {
            debugLog("Returning cached classification for:", cacheKey);
            return this.cache.get(cacheKey);
        }

        if (!areGeoLibsLoaded()) {
            debugLog(
                "⚠️ Libraries not ready, deferring classification for:",
                layerConfig.name,
            );
            return null;
        }

        debugLog("Computing classification for:", cacheKey);

        const indicator = layerConfig.attribute_field_name;
        const bounds = population?.bounds;
        const drawn = population?.values || this._values(layerConfig, data);
        const seed =
            population?.quantiles || (bounds ? [bounds.min, bounds.max] : null);
        const values = drawn.length || !seed ? drawn : seed;
        const mode = layerConfig.classification;
        const requested = layerConfig.nb_class || DEFAULT_NUM_CLASSES;
        const numClasses =
            mode === INTERVAL && bounds
                ? requested
                : Math.min(
                      requested,
                      mode === QUANTILE
                          ? values.length - 1
                          : Math.max(1, values.length),
                  );
        if (numClasses < 1) {
            debugLog("Too few values to classify:", layerConfig.name);
            return null;
        }
        const opacity = layerConfig.layer_opacity ?? 1;
        const beginColorHex = layerConfig.begin_color || DEFAULT_BEGIN_COLOR;
        const endColorHex = layerConfig.end_color || DEFAULT_END_COLOR;
        const beginColor = chroma(beginColorHex).alpha(opacity).css();
        const endColor = chroma(endColorHex).alpha(opacity).css();

        let scale = chroma.scale([beginColor, endColor]);
        const series = new geostats(values);

        let classValues = null;
        let legendLabels = null;
        let classCount = 0;

        switch (mode) {
            case UNIQUE:
                classValues = series.getClassUniqueValues();
                legendLabels = classValues.map(String);
                classCount = classValues.length;
                scale = chroma.scale("RdYlBu").domain([0, classCount], classCount);
                break;
            case QUANTILE:
            case INTERVAL:
                if (mode === QUANTILE && population?.quantiles) {
                    series.setBounds(population.quantiles);
                    series.setRanges();
                } else if (mode === QUANTILE) {
                    series.getClassQuantile(numClasses);
                } else {
                    series.getClassEqInterval(
                        numClasses,
                        population?.bounds?.min,
                        population?.bounds?.max,
                    );
                }
                classValues = series.bounds.map(Number);
                legendLabels = series.getRanges();
                classCount = classValues.length - 1;
                scale = scale.domain([0, classCount], classCount);
                break;
        }

        if (!classValues || classCount < 1) {
            debugLog("Unusable classification, skipping:", mode);
            return null;
        }

        const colors = scale
            .colors(classCount)
            .map((color) => toRgbaString(chroma(color).alpha(opacity)));

        let legend = null;
        if (classCount <= LEGEND_MAX_ITEMS) {
            legend = legendHtml(layerConfig.name, legendLabels, colors);
        }

        const result = {
            mode,
            values: classValues,
            colors,
            legendLabels,
            legend,
            indicator,
            opacity,
        };

        this.cache.set(cacheKey, result);

        return result;
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @returns {Object}
     */
    _proportional(layerConfig, data, population) {
        if (!areGeoLibsLoaded()) {
            debugLog(
                "⚠️ Libraries not ready, deferring proportional classification for:",
                layerConfig.name,
            );
            return null;
        }

        const cacheKey = [
            "proportion",
            layerConfig.resId,
            layerConfig.attribute_field_name,
            layerConfig.min_size,
            layerConfig.max_size,
            layerConfig.begin_color,
            layerConfig.layer_opacity,
            this._dataFingerprint(data, layerConfig.attribute_field_name),
            this._populationFingerprint(population),
        ].join("_");
        if (this.cache.has(cacheKey)) {
            return this.cache.get(cacheKey);
        }

        const indicator = layerConfig.attribute_field_name;
        const values = this._values(layerConfig, data);
        const series = new geostats(values);
        const minSize = layerConfig.min_size || DEFAULT_MIN_SIZE;
        const maxSize = layerConfig.max_size || DEFAULT_MAX_SIZE;
        const minValue = population?.bounds?.min ?? series.min();
        const maxValue = population?.bounds?.max ?? series.max();
        const colorHex = layerConfig.begin_color || DEFAULT_BEGIN_COLOR;
        const opacity = layerConfig.layer_opacity ?? 1;
        const color = toRgbaString(chroma(colorHex).alpha(opacity));

        const result = {
            indicator,
            color,
            minSize,
            maxSize,
            minValue,
            maxValue,
        };
        this.cache.set(cacheKey, result);
        return result;
    }

    /**
     * @param {Array} data
     * @returns {string}
     */
    _dataFingerprint(data, attributeField) {
        if (!data || data.length === 0) {
            return "empty";
        }

        const firstId = this._recordId(data[0]);
        const lastId = this._recordId(data[data.length - 1]);
        let fingerprint = `${data.length}_${firstId}_${lastId}`;

        if (attributeField) {
            let acc = 0;
            for (const item of data) {
                const value = classValue(savedValue(item, attributeField));
                acc = (acc * 31 + valueHash(value)) % 2147483647;
            }
            fingerprint += `_${acc}`;
        }
        return fingerprint;
    }

    /**
     * @param {Object} record
     * @returns {number|string}
     */
    _recordId(record) {
        if (record.resId !== undefined) {
            return record.resId;
        }
        if (record.id !== undefined) {
            return record.id;
        }
        return "unknown";
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @returns {Array}
     */
    _values(layerConfig, data) {
        const attributeFieldName = layerConfig.attribute_field_name;
        return data
            .map((item) => classValue(savedValue(item, attributeFieldName)))
            .filter((value) => value !== null);
    }
}
