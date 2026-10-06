// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { sortBy } from "@web/core/utils/collections/arrays";
import { InFlight, KeepLast, SupersededError } from "@web/core/utils/concurrency";
import { Model } from "@web/model/model";
import { addPropertyFieldDefs } from "@web/model/property_fields";
import { rankInterval } from "@web/search/utils/dates";
import { getGroupBy } from "@web/search/utils/group_by";
import { GROUPABLE_TYPES } from "@web/search/utils/misc";
import {
    applyCurrencyFallback,
    foldCumulatedStart,
    getGroupLabels,
    getMeasureAggregatorOf,
    getMeasureSpec,
    getOverlappingSeriesGroupBy,
    getRawValue,
    isAdditiveAggregator,
    makeDataPoint,
    sumStackedDatasets,
} from "@web/views/graph/graph_data_points";
import {
    computeReportMeasures,
    processMeasure,
    visibleArchGroupBys,
} from "@web/views/view_measurements";

export const SEP = " / ";
export const DATA_LIMIT = 80;

const SEQUENTIAL_TYPES = ["date", "datetime"];

/** @typedef {import("@web/model/types").SearchParams} SearchParams */

const log = makeLogger("web.view.graph");

export class GraphModel extends Model {
    /** @override */
    setup(params) {
        this.keepLast = new KeepLast({ rejectSuperseded: true });
        this.fetches = new InFlight();
        /** @type {any} */
        const _fetchDataPoints = this._fetchDataPoints.bind(this);
        this._fetchDataPoints = (...args) =>
            this.fetches.track(_fetchDataPoints(...args));

        this.initialGroupBy = null;
        this.contextParamsSeen = {};
        this.pendingContextSettings = {};

        // a copy: the view's modelParams are its props, and a reactive model
        // writing into them would re-render the view and reload
        this.metaData = { ...params };
        this.data = null;
        this.searchParams = null;
        this.lineOverlayDataset = null;
        this.seriesOverlap = false;
        this.forceAllDataPoints = false;
    }

    /**
     * Whether the chart stacks its series: the user's choice, unless a series
     * level is multi-valued, where a stack would count a record once per
     * series it is in and rise above the real total.
     *
     * @returns {boolean}
     */
    get isStacked() {
        return Boolean(this.metaData.stacked) && !this.seriesOverlap;
    }

    /**
     * @param {Object} context
     * @returns {ReturnType<typeof visibleArchGroupBys>}
     */
    _visibleArchGroupBy(context) {
        const { fieldAttrs, groupBy } = this.metaData;
        return visibleArchGroupBys(groupBy, fieldAttrs, context);
    }

    /** @param {SearchParams} searchParams */
    load(searchParams) {
        return this.fetches.track(this._loadSearchParams(searchParams));
    }

    /** @param {SearchParams} searchParams */
    async _loadSearchParams(searchParams) {
        const previousSearchParams = this.searchParams;
        this.searchParams = searchParams;
        if (
            this.forceAllDataPoints &&
            previousSearchParams &&
            (JSON.stringify(previousSearchParams.domain) !==
                JSON.stringify(searchParams.domain) ||
                JSON.stringify(previousSearchParams.groupBy) !==
                    JSON.stringify(searchParams.groupBy))
        ) {
            this.forceAllDataPoints = false;
        }
        if (!this.initialGroupBy) {
            this.initialGroupBy =
                searchParams.context.graph_groupbys ||
                this._visibleArchGroupBy(searchParams.context);
        }
        this._consumeContextParams(searchParams.context);
        const metaData = this._buildMetaData(undefined, {
            ...this.metaData,
            ...this.pendingContextSettings,
        });
        log.pipeline("load", () => ({
            resModel: metaData.resModel,
            mode: metaData.mode,
            measure: metaData.measure,
            groupBy: metaData.groupBy.map((gb) => gb.spec),
            domain: searchParams.domain,
        }));
        let generation;
        const properties = this.keepLast.add(
            addPropertyFieldDefs(
                this.orm,
                metaData.resModel,
                searchParams.context,
                metaData.fields,
                metaData.groupBy.map((gb) => gb.fieldName),
                () => generation === this.keepLast.generation,
            ),
        );
        generation = this.keepLast.generation;
        try {
            await properties;
        } catch (error) {
            if (!(error instanceof SupersededError)) {
                throw error;
            }
            log.logic("property load superseded");
            return;
        }
        if (generation !== this.keepLast.generation) {
            return;
        }
        await this._fetchDataPoints(metaData);
    }

    async forceLoadAll() {
        while (this.fetches.isBusy) {
            await this.fetches.whenIdle();
        }
        this.forceAllDataPoints = true;
        this.prepareData();
        this.notify();
    }

    /** @override */
    hasData() {
        return /** @type {any} */ (this).dataPoints?.length > 0;
    }

    /** @param {Object} params */
    async updateMetaData(params) {
        if ("measure" in params) {
            const metaData = this._buildMetaData(params);
            if (!(await this._fetchDataPoints(metaData))) {
                return;
            }
            this.useSampleModel = false;
        } else {
            while (this.fetches.isBusy) {
                await this.fetches.whenIdle();
            }
            this.metaData = { ...this.metaData, ...params };
            this.prepareData();
        }
        this.notify();
    }

    /**
     * Collects the context's new graph_* keys in pendingContextSettings: the
     * load that commits its data points publishes them, and a superseded load
     * leaves them for the next one, since they are marked seen already.
     *
     * @protected
     * @param {Object} context
     */
    _consumeContextParams(context) {
        const pending = this.pendingContextSettings;
        const mode = () => pending.mode ?? this.metaData.mode;
        const seen = this.contextParamsSeen;
        const changed = (key) => {
            if (context[key] === seen[key]) {
                return false;
            }
            seen[key] = context[key];
            return true;
        };
        const measureChanged = changed("graph_measure");
        const modeChanged = changed("graph_mode");
        const orderChanged = changed("graph_order");
        const stackedChanged = changed("graph_stacked");
        const cumulatedChanged = changed("graph_cumulated");
        if (measureChanged && context.graph_measure) {
            pending.measure = context.graph_measure;
        }
        if (modeChanged && context.graph_mode) {
            pending.mode = context.graph_mode;
        }
        if (mode() !== "pie" && mode() !== "scatter") {
            if (orderChanged && "graph_order" in context) {
                pending.order = context.graph_order;
            }
            if (stackedChanged && "graph_stacked" in context) {
                pending.stacked = context.graph_stacked;
            }
            if (mode() === "line" && cumulatedChanged && "graph_cumulated" in context) {
                pending.cumulated = context.graph_cumulated;
            }
        }
    }

    /**
     * @protected
     * @param {Object} [params={}]
     * @param {Object} [base] the metaData to build on, the published one by default
     * @returns {Object}
     */
    _buildMetaData(params, base = this.metaData) {
        const { domain, context, groupBy } = this.searchParams;

        const metaData = { ...base, context };
        metaData.domain = domain;
        metaData.groupBy = groupBy.length ? groupBy : this.initialGroupBy;

        this._normalize(metaData);

        metaData.measures = computeReportMeasures(
            metaData.fields,
            metaData.fieldAttrs,
            [...(metaData.viewMeasures || []), metaData.measure],
        );
        if (metaData.measure !== "__count" && !metaData.measures[metaData.measure]) {
            console.warn(
                `Measure "${metaData.measure}" has no field definition (removed or renamed field?); falling back to Count.`,
            );
            metaData.measure = "__count";
        }

        return Object.assign(metaData, params);
    }

    /**
     * @protected
     * @param {Object} metaData
     * @returns {Promise<boolean>}
     */
    async _fetchDataPoints(metaData) {
        let dataPoints;
        const endFetch = log.perf(`loadDataPoints ${metaData.resModel}`);
        try {
            dataPoints = await this.keepLast.add(this.loadDataPoints(metaData));
        } catch (error) {
            if (error instanceof SupersededError) {
                endFetch({ superseded: true });
                return false;
            }
            endFetch({ failed: true });
            throw error;
        }
        endFetch({ dataPoints: dataPoints.length });
        /** @type {any} */ (this).dataPoints = dataPoints;
        this.metaData = metaData;
        this.pendingContextSettings = {};
        this.prepareData();
        return true;
    }

    /**
     * @protected
     * @param {Object[]} dataPoints
     * @param {boolean} forceUseAllDataPoints
     * @returns {Object}
     */
    _getData(dataPoints, forceUseAllDataPoints) {
        const { mode } = this.metaData;

        const dataPtMapping = new WeakMap();
        const datasetsTmp = {};
        let exceeds = false;

        const labels = [];
        const labelMap = {};
        for (const dataPt of dataPoints) {
            const datasetLabel = this._getDatasetLabel(dataPt);
            const datasetKey =
                mode === "pie" ? datasetLabel : (dataPt.datasetId ?? datasetLabel);
            const isNewDataset = !(datasetKey in datasetsTmp);

            const x = dataPt.labels.slice(0, mode === "pie" ? undefined : 1);
            const trueLabel = x.length ? x.join(SEP) : _t("Total");
            const key =
                mode === "pie"
                    ? (dataPt.identifier ?? JSON.stringify(x))
                    : (dataPt.xIdentifier ?? JSON.stringify(x));
            const isNewLabel = labelMap[key] === undefined;

            if (
                !forceUseAllDataPoints &&
                ((isNewDataset && Object.keys(datasetsTmp).length >= DATA_LIMIT) ||
                    (isNewLabel && labels.length >= DATA_LIMIT))
            ) {
                exceeds = true;
                continue;
            }
            if (isNewDataset) {
                datasetsTmp[datasetKey] = { label: datasetLabel };
            }
            dataPtMapping.set(dataPt, datasetsTmp[datasetKey]);

            if (isNewLabel) {
                labelMap[key] = labels.length;
                labels.push(trueLabel);
            }
            dataPt.labelIndex = labelMap[key];
            dataPt.trueLabel = trueLabel;
        }

        for (const dataPt of dataPoints) {
            if (!dataPtMapping.has(dataPt)) {
                continue;
            }

            const {
                domain,
                labelIndex,
                trueLabel,
                value,
                identifier,
                cumulatedStart,
                currencyId,
            } = dataPt;
            const dataset = dataPtMapping.get(dataPt);
            if (!dataset.data) {
                const dataLength = labels.length;
                Object.assign(dataset, {
                    data: new Array(dataLength).fill(0),
                    cumulatedStart,
                    trueLabels: labels.slice(0, dataLength),
                    domains: Array.from({ length: dataLength }, () => []),
                    identifiers: new Set(),
                    currencyIds: new Array(dataLength).fill(undefined),
                });
            }
            dataset.data[labelIndex] = value;
            dataset.domains[labelIndex] = domain;
            dataset.trueLabels[labelIndex] = trueLabel;
            dataset.identifiers.add(identifier);
            dataset.currencyIds[labelIndex] = currencyId;
        }

        const datasets = Object.values(datasetsTmp);

        return { datasets, labels, exceeds };
    }

    getLineOverlayDataset() {
        const { fields, measure } = this.metaData;
        const datasets = this.data.datasets;
        if (!this.isStacked || datasets.length < 2) {
            return null;
        }
        const aggregator = getMeasureAggregatorOf(measure, fields);
        const additive = isAdditiveAggregator(aggregator);
        log.logic("lineOverlay", () => ({
            measure,
            aggregator,
            additive,
            datasets: datasets.length,
        }));
        if (!additive) {
            return null;
        }
        const { data, currencyIds } = sumStackedDatasets(datasets);
        if (currencyIds.includes(false)) {
            log.logic("lineOverlay:unknownCurrency", () => ({
                indexes: currencyIds
                    .flatMap((currencyId, index) =>
                        currencyId === false ? [index] : [],
                    )
                    .join(","),
            }));
        }
        return {
            label: _t("Sum"),
            data,
            currencyIds,
            trueLabels: datasets[0].trueLabels,
        };
    }

    /**
     * @protected
     * @param {Object} dataPoint
     * @returns {string}
     */
    _getDatasetLabel(dataPoint) {
        const { measure, measures, mode } = this.metaData;
        const { labels } = dataPoint;
        if (mode === "pie") {
            return "";
        }
        return labels.slice(1).join(SEP) || measures[measure].string;
    }

    /**
     * @protected
     * @returns {string}
     */
    _getDefaultFilterLabel(gb) {
        return this.metaData.fields[gb?.fieldName]?.falsy_value_label || _t("None");
    }

    /**
     * @protected
     * @returns {Object[]}
     */
    _getProcessedDataPoints() {
        const { groupBy, mode, order, cumulated } = this.metaData;
        let processedDataPoints;
        /** @type {any[]} */
        const dataPoints = /** @type {any} */ (this).dataPoints;
        if (mode === "line" || mode === "scatter") {
            processedDataPoints = dataPoints.filter(
                (dataPoint) => !dataPoint.isFalsyXGroup,
            );
        } else if (mode === "pie") {
            processedDataPoints = dataPoints.filter(
                (dataPoint) => dataPoint.value > 0 && dataPoint.count !== 0,
            );
        } else {
            processedDataPoints = dataPoints.filter(
                (dataPoint) => dataPoint.count !== 0,
            );
        }

        if (order !== null && mode !== "pie" && groupBy.length && !cumulated) {
            const groupedDataPoints = Object.groupBy(
                processedDataPoints,
                (dataPt) => dataPt.xIdentifier ?? dataPt.labels[0],
            );
            const groups = Object.values(groupedDataPoints);
            const groupTotal = (group) =>
                group.reduce((sum, dataPt) => sum + dataPt.value, 0);
            processedDataPoints = sortBy(
                groups,
                groupTotal,
                order.toLowerCase(),
            ).flat();
        }

        return processedDataPoints;
    }

    /**
     * @protected
     * @param {Object} metaData
     * @returns {Promise<any[]>}
     */
    async loadDataPoints(metaData) {
        metaData.allIntegers = true;
        const { measure, domain, fields, groupBy, resModel, cumulatedStart } = metaData;
        const xFieldName = groupBy[0]?.fieldName;
        const sequentialField =
            cumulatedStart && SEQUENTIAL_TYPES.includes(fields[xFieldName]?.type)
                ? xFieldName
                : null;
        const { measures, fieldAggregate, monetaryAggregates } = getMeasureSpec(
            measure,
            fields,
        );

        const groups = await this.orm.formattedReadGroup(
            resModel,
            domain,
            groupBy.map((gb) => gb.spec),
            measures,
            {
                context: { fill_temporal: true, ...this.searchParams.context },
            },
        );

        const graphCurrencies = new Set();
        const defaultCurrency = user.activeCompany?.currency_id;
        const startGroups = await this._fetchStartGroups(
            metaData,
            sequentialField,
            measures,
            groups,
        );
        const { cumulatedStartValue, cumulatedStartConverted } = startGroups
            ? foldCumulatedStart(startGroups, {
                  groupBy,
                  sequentialField,
                  fieldAggregate,
                  monetaryAggregates,
                  defaultCurrency,
                  graphCurrencies,
              })
            : { cumulatedStartValue: {}, cumulatedStartConverted: {} };

        /** @type {import("./graph_data_points").GraphSeriesContext} */
        const series = {
            fieldAggregate,
            monetaryAggregates,
            defaultCurrency,
            graphCurrencies,
            cumulatedStartValue,
            cumulatedStartConverted,
        };
        /** @type {import("./graph_data_points").Numbering} */
        const numbering = {};
        const getDefaultFilterLabel = (gb) => this._getDefaultFilterLabel(gb);
        const dataPoints = [];
        for (const group of groups) {
            if (!Number.isInteger(getRawValue(group, fieldAggregate))) {
                metaData.allIntegers = false;
            }
            const { labels, rawValues, isFalsyXGroup } = getGroupLabels(group, {
                groupBy,
                fields,
                numbering,
                getDefaultFilterLabel,
            });
            dataPoints.push(
                makeDataPoint(group, { labels, rawValues, isFalsyXGroup }, series),
            );
        }
        const hasConvertedValues = Boolean(monetaryAggregates?.[1]);
        if (monetaryAggregates) {
            log.logic("currencyFallback", () => ({
                fieldAggregate,
                hasConvertedValues,
                graphCurrencies: [...graphCurrencies].join(","),
                defaultCurrency,
            }));
        }
        return applyCurrencyFallback(dataPoints, {
            graphCurrencies,
            defaultCurrency,
            hasConvertedValues,
        });
    }

    /**
     * @protected
     * @param {Object} metaData
     * @param {string | null} sequentialField
     * @param {string[]} measures
     * @param {Object[]} groups
     * @returns {Promise<any>}
     */
    async _fetchStartGroups(metaData, sequentialField, measures, groups) {
        const { domain, groupBy, resModel, cumulatedStart } = metaData;
        if (!cumulatedStart || !sequentialField) {
            return false;
        }
        const sequentialSpec = groupBy[0].spec;
        const firstDatedGroup = groups.find((group) => group[sequentialSpec]);
        if (
            !firstDatedGroup ||
            !domain.some((leaf) => leaf.length === 3 && leaf[0] === sequentialField)
        ) {
            return false;
        }
        const firstDate = firstDatedGroup[sequentialSpec][0];
        const newDomain = Domain.combine(
            [
                new Domain([[sequentialField, "<", firstDate]]),
                Domain.removeDomainLeaves(domain, [sequentialField]),
            ],
            "AND",
        ).toList();
        return this.orm.formattedReadGroup(
            resModel,
            newDomain,
            groupBy
                .filter((gb) => gb.fieldName !== sequentialField)
                .map((gb) => gb.spec),
            measures,
            {
                context: { ...this.searchParams.context },
            },
        );
    }

    /**
     * @protected
     * @param {Object} metaData
     */
    _normalize(metaData) {
        const { fields } = metaData;
        const groupBy = [];
        for (const gb of metaData.groupBy) {
            let ngb = gb;
            if (typeof gb === "string") {
                const baseName = gb.split(":")[0];
                if (!baseName.includes(".") && !fields[baseName]) {
                    console.warn(
                        `Group by "${gb}" has no field definition (removed or renamed field?); ignoring it.`,
                    );
                    continue;
                }
                ngb = getGroupBy(gb, fields);
            }
            groupBy.push(ngb);
        }

        const processedGroupBy = [];
        for (const gb of groupBy) {
            const { fieldName, interval } = gb;
            if (!fieldName.includes(".")) {
                const { groupable, type } = fields[fieldName];
                if (
                    !groupable ||
                    ["id", "__count"].includes(fieldName) ||
                    !GROUPABLE_TYPES.includes(type)
                ) {
                    continue;
                }
            }
            const index = processedGroupBy.findIndex(
                (gb) => gb.fieldName === fieldName,
            );
            if (index === -1) {
                processedGroupBy.push(gb);
            } else if (interval) {
                const registeredInterval = processedGroupBy[index].interval;
                if (rankInterval(registeredInterval) < rankInterval(interval)) {
                    processedGroupBy.splice(index, 1, gb);
                }
            }
        }
        metaData.groupBy = processedGroupBy;

        metaData.measure = processMeasure(metaData.measure);
    }

    /** @protected */
    prepareData() {
        const processedDataPoints = this._getProcessedDataPoints();
        this.data = this._getData(processedDataPoints, this.forceAllDataPoints);
        const { fields, groupBy, mode, stacked } = this.metaData;
        const overlapping =
            mode === "pie" ? null : getOverlappingSeriesGroupBy(groupBy, fields);
        this.seriesOverlap = Boolean(overlapping);
        log.logic("seriesOverlap", () => ({
            mode,
            stacked,
            overlappingGroupBy: overlapping?.spec ?? null,
            overlappingType: overlapping ? fields[overlapping.fieldName].type : null,
            isStacked: this.isStacked,
        }));
        this.lineOverlayDataset = null;
        if (this.metaData.mode === "bar") {
            this.lineOverlayDataset = this.getLineOverlayDataset();
        }
    }
}
