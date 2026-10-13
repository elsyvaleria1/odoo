// @ts-check
/** @odoo-module native */

import {
    getCurrencyAggregateSpecs,
    getMeasureAggregator,
} from "@web/views/view_measurements";

/** @typedef {Record<string, any>} ServerGroup */

/** @typedef {Record<string, any>} FieldsMap */

/** @typedef {{ fieldName: string, spec: string, [key: string]: any }} GroupByLevel */

/** @typedef {Record<string, Record<string, number>>} Numbering */

/**
 * @typedef {{
 * count: any,
 * domain: any,
 * value: any,
 * labels: any[],
 * isFalsyXGroup: boolean,
 * identifier: string,
 * xIdentifier: string,
 * datasetId: string,
 * cumulatedStart: any,
 * convertedCumulatedStart?: any,
 * currencyId?: any,
 * convertedValue?: any,
 * }} GraphDataPoint
 */

/**
 * @typedef {{
 * currencyId?: any,
 * value?: any,
 * cumulatedStart?: any,
 * convertedValue?: any,
 * convertedCumulatedStart?: any,
 * [key: string]: any,
 * }} CurrencyResolvable
 */

/**
 * @param {string} measure
 * @param {FieldsMap} fields
 * @returns {{measures: string[], fieldAggregate: string, monetaryAggregates: string[] | undefined}}
 */
export function getMeasureSpec(measure, fields) {
    const measures = ["__count"];
    if (measure === "__count") {
        return { measures, fieldAggregate: "__count", monetaryAggregates: undefined };
    }
    const field = fields[measure];
    const aggregator = getMeasureAggregator(measure, field);
    let monetaryAggregates;
    const currencySpecs = getCurrencyAggregateSpecs(field, aggregator);
    if (currencySpecs) {
        const { currencySpec, convertedSpec } = currencySpecs;
        monetaryAggregates = convertedSpec
            ? [currencySpec, convertedSpec]
            : [currencySpec];
        measures.push(...monetaryAggregates);
    }
    const fieldAggregate = `${measure}:${aggregator}`;
    measures.push(fieldAggregate);
    return { measures, fieldAggregate, monetaryAggregates };
}

/**
 * @param {ServerGroup} group
 * @param {string[]} monetaryAggregates
 * @returns {any[]}
 */
export function getGroupCurrencies(group, monetaryAggregates) {
    return (group[monetaryAggregates[0]] || []).filter(
        (/** @type {any} */ currencyId) => currencyId != null,
    );
}

/**
 * @param {ServerGroup[]} startGroups
 * @param {Object} params
 * @param {GroupByLevel[]} params.groupBy
 * @param {string | null} params.sequentialField
 * @param {string} params.fieldAggregate
 * @param {string[]} [params.monetaryAggregates]
 * @param {any} [params.defaultCurrency]
 * @param {Set<any>} params.graphCurrencies
 * @returns {{cumulatedStartValue: Record<string, any>, cumulatedStartConverted: Record<string, any>}}
 */
export function foldCumulatedStart(
    startGroups,
    {
        groupBy,
        sequentialField,
        fieldAggregate,
        monetaryAggregates,
        defaultCurrency,
        graphCurrencies,
    },
) {
    /** @type {Record<string, any>} */
    const cumulatedStartValue = {};
    /** @type {Record<string, any>} */
    const cumulatedStartConverted = {};
    const keptGroupBy = groupBy.filter((gb) => gb.fieldName !== sequentialField);
    for (const group of startGroups) {
        const rawValues = keptGroupBy.map((gb) => ({ [gb.spec]: group[gb.spec] }));
        const key = JSON.stringify(rawValues);
        let value = group[fieldAggregate];
        if (monetaryAggregates) {
            const currencies = getGroupCurrencies(group, monetaryAggregates);
            const convertedSpec = monetaryAggregates[1];
            cumulatedStartConverted[key] = convertedSpec && group[convertedSpec];
            if (currencies.length > 1) {
                if (convertedSpec) {
                    value = cumulatedStartConverted[key];
                    graphCurrencies.add(defaultCurrency);
                }
            } else if (currencies.length === 1) {
                graphCurrencies.add(currencies[0]);
            }
        }
        cumulatedStartValue[key] = value;
    }
    return { cumulatedStartValue, cumulatedStartConverted };
}

/**
 * @param {any} val
 * @param {GroupByLevel} gb
 * @param {FieldsMap} fields
 * @param {Numbering} numbering
 * @param {(gb: GroupByLevel) => string} getDefaultFilterLabel
 * @returns {any}
 */
export function getValueLabel(val, gb, fields, numbering, getDefaultFilterLabel) {
    const { fieldName } = gb;
    const { type } = fields[fieldName];
    if (type === "boolean") {
        return `${val}`;
    }
    if (type === "integer") {
        return val === false ? "0" : `${val}`;
    }
    if (val === false) {
        return getDefaultFilterLabel(gb);
    }
    if (["many2many", "many2one"].includes(type)) {
        const [id, name] = val;
        const key = JSON.stringify([fieldName, name]);
        if (!numbering[key]) {
            numbering[key] = {};
        }
        const numbers = numbering[key];
        if (!numbers[id]) {
            numbers[id] = Object.keys(numbers).length + 1;
        }
        const num = numbers[id];
        return num === 1 ? name : `${name} (${num})`;
    }
    if (type === "selection") {
        const selected = fields[fieldName].selection.find(
            (/** @type {[any, string]} */ s) => s[0] === val,
        );
        return selected ? selected[1] : String(val);
    }
    if (["date", "datetime"].includes(type)) {
        return val[1];
    }
    return val;
}

/**
 * @param {ServerGroup} group
 * @param {Object} params
 * @param {GroupByLevel[]} params.groupBy
 * @param {FieldsMap} params.fields
 * @param {Numbering} params.numbering
 * @param {(gb: GroupByLevel) => string} params.getDefaultFilterLabel
 * @returns {{labels: any[], rawValues: Record<string, any>[], isFalsyXGroup: boolean}}
 */
export function getGroupLabels(
    group,
    { groupBy, fields, numbering, getDefaultFilterLabel },
) {
    const labels = [];
    /** @type {Record<string, any>[]} */
    const rawValues = [];
    let isFalsyXGroup = false;
    for (const [gbIndex, gb] of groupBy.entries()) {
        const val = group[gb.spec];
        rawValues.push({ [gb.spec]: val });
        if (val === false && gbIndex === 0) {
            const { type } = fields[gb.fieldName];
            if (type !== "boolean" && type !== "integer") {
                isFalsyXGroup = true;
            }
        }
        labels.push(getValueLabel(val, gb, fields, numbering, getDefaultFilterLabel));
    }
    return { labels, rawValues, isFalsyXGroup };
}

/**
 * @param {ServerGroup} group
 * @param {string} fieldAggregate
 * @returns {any}
 */
export function getRawValue(group, fieldAggregate) {
    return group[fieldAggregate] === false ? 0 : group[fieldAggregate];
}

/**
 * @typedef {Object} GraphSeriesContext
 * @property {string} fieldAggregate
 * @property {string[]} [monetaryAggregates]
 * @property {any} [defaultCurrency]
 * @property {Set<any>} graphCurrencies
 * @property {Record<string, any>} cumulatedStartValue
 * @property {Record<string, any>} cumulatedStartConverted
 */

/**
 * @param {ServerGroup} group
 * @param {Object} groupInfo
 * @param {any[]} groupInfo.labels
 * @param {Record<string, any>[]} groupInfo.rawValues
 * @param {boolean} groupInfo.isFalsyXGroup
 * @param {GraphSeriesContext} series
 * @returns {GraphDataPoint}
 */
export function makeDataPoint(
    group,
    { labels, rawValues, isFalsyXGroup },
    {
        fieldAggregate,
        monetaryAggregates,
        defaultCurrency,
        graphCurrencies,
        cumulatedStartValue,
        cumulatedStartConverted,
    },
) {
    const { __domain, __count } = group;
    const groupId = JSON.stringify(rawValues.slice(1));
    /** @type {GraphDataPoint} */
    const dataPoint = {
        count: __count,
        domain: __domain,
        value: getRawValue(group, fieldAggregate),
        labels,
        isFalsyXGroup,
        identifier: JSON.stringify(rawValues),
        xIdentifier: JSON.stringify(rawValues.slice(0, 1)),
        datasetId: groupId,
        cumulatedStart: cumulatedStartValue[groupId] || 0,
        convertedCumulatedStart: cumulatedStartConverted[groupId] || 0,
    };
    if (monetaryAggregates) {
        const currencies = getGroupCurrencies(group, monetaryAggregates);
        const convertedSpec = monetaryAggregates[1];
        dataPoint.currencyId = currencies[0];
        dataPoint.convertedValue = convertedSpec && group[convertedSpec];
        if (currencies.length > 1) {
            if (convertedSpec) {
                dataPoint.currencyId = defaultCurrency;
                dataPoint.value = dataPoint.convertedValue;
            } else {
                dataPoint.currencyId = false;
            }
        }
        if (dataPoint.currencyId !== false && currencies.length && __count !== 0) {
            graphCurrencies.add(dataPoint.currencyId);
        }
    }
    return dataPoint;
}

const ADDITIVE_AGGREGATORS = new Set(["sum", "count"]);

const MULTI_VALUED_TYPES = new Set(["many2many", "one2many", "tags"]);

/**
 * @param {GroupByLevel[]} groupBy
 * @param {FieldsMap} fields
 * @returns {GroupByLevel | null}
 */
export function getOverlappingSeriesGroupBy(groupBy, fields) {
    return (
        groupBy
            .slice(1)
            .find((gb) => MULTI_VALUED_TYPES.has(fields[gb.fieldName]?.type)) ?? null
    );
}

/**
 * @param {string} measure
 * @param {FieldsMap} fields
 * @returns {string}
 */
export function getMeasureAggregatorOf(measure, fields) {
    return measure === "__count"
        ? "count"
        : getMeasureAggregator(measure, fields[measure]);
}

/**
 * @param {string} aggregator
 * @returns {boolean}
 */
export function isAdditiveAggregator(aggregator) {
    return ADDITIVE_AGGREGATORS.has(aggregator);
}

/**
 * @param {any[]} currencyIds
 * @returns {any}
 */
function mergeCurrencies(currencyIds) {
    const known = new Set(currencyIds.filter((currencyId) => currencyId != null));
    if (known.has(false) || known.size > 1) {
        return false;
    }
    return known.values().next().value;
}

/**
 * @param {{ data: number[], currencyIds: any[] }[]} datasets
 * @returns {{ data: number[], currencyIds: any[] }}
 */
export function sumStackedDatasets(datasets) {
    const length = Math.max(...datasets.map((dataset) => dataset.data.length));
    const data = [];
    const currencyIds = [];
    for (let i = 0; i < length; i++) {
        data.push(datasets.reduce((sum, dataset) => sum + (dataset.data[i] || 0), 0));
        currencyIds.push(
            mergeCurrencies(datasets.map((dataset) => dataset.currencyIds[i])),
        );
    }
    return { data, currencyIds };
}

/**
 * @param {CurrencyResolvable[]} dataPoints
 * @param {Object} params
 * @param {Set<any>} params.graphCurrencies
 * @param {any} [params.defaultCurrency]
 * @param {boolean} params.hasConvertedValues
 * @returns {CurrencyResolvable[]}
 */
export function applyCurrencyFallback(
    dataPoints,
    { graphCurrencies, defaultCurrency, hasConvertedValues },
) {
    for (const dataPoint of dataPoints) {
        if (graphCurrencies.size > 1 && hasConvertedValues) {
            dataPoint.currencyId = defaultCurrency;
            dataPoint.value = dataPoint.convertedValue;
            dataPoint.cumulatedStart = dataPoint.convertedCumulatedStart;
        }
        delete dataPoint.convertedValue;
        delete dataPoint.convertedCumulatedStart;
    }
    return dataPoints;
}
