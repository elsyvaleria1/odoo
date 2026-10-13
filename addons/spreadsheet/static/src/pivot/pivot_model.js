/** @odoo-module native */
//@ts-check

import {
    constants,
    EvaluationError,
    helpers,
    SpreadsheetPivotTable,
} from "@odoo/o-spreadsheet";
import { Domain } from "@web/core/domain";
import { _t } from "@web/core/translation";
import { getLeafCounts, PivotModel } from "@web/views/pivot";

import { parseGroupField } from "./pivot_helpers.js";

const {
    toNormalizedPivotValue,
    toNumber,
    isDateOrDatetimeField,
    pivotTimeAdapter,
    deepEquals,
} = helpers;
const { DEFAULT_LOCALE } = constants;

/**
 * @typedef {import("@odoo/o-spreadsheet").PivotTableColumn} PivotTableColumn
 * @typedef {import("@odoo/o-spreadsheet").PivotTableRow} PivotTableRow
 * @typedef {import("@odoo/o-spreadsheet").PivotDomain} PivotDomain
 * @typedef {import("@odoo/o-spreadsheet").PivotMeasure} PivotMeasure
 */

export const NO_RECORD_AT_THIS_POSITION = "__NO_RECORD_AT_THIS_POSITION__";

/** @extends {PivotModel<{_t: typeof import("@web/core/translation")._t}>} */
export class OdooPivotModel extends PivotModel {
    /**
     * @param {{_t: typeof import("@web/core/translation")._t}} env
     * @param {import("@spreadsheet").OdooPivotModelParams} params
     * @param {import("@spreadsheet").PivotModelServices} services
     */
    constructor(env, params, services) {
        const webParams = params.definition.getDefinitionForPivotModel(params.fields);
        webParams.searchParams = { ...webParams.searchParams, ...params.searchParams };
        super(env, webParams, services);
        this.definition = params.definition;
        /**
         * @private
         */
        this._displayNames = {};
        /**
         * @private
         */
        this._displayLabels = {};
        /**
         * @private
         * @type {import("@spreadsheet/data_sources/server_data").ServerData}
         */
        this.serverData = services.serverData;

        /**
         * @type {import("@spreadsheet").OdooGetters}
         */
        this.getters = services.getters;
    }

    /** @param {PivotMeasure[]} measures */
    updateMeasures(measures) {
        for (const measure of this.definition.measures) {
            const updatedMeasure = measures.find((m) => m.id === measure.id);
            if (!updatedMeasure || updatedMeasure.computedBy) {
                continue;
            }
            if (
                updatedMeasure.fieldName !== measure.fieldName ||
                updatedMeasure.aggregator !== measure.aggregator
            ) {
                throw new Error("Measures fieldName or aggregator cannot be updated");
            }
        }
        this.definition.measures = measures;
        this.resetTableStructure();
    }

    updateSortColumn(sortedColumn) {
        this.definition.sortedColumn = sortedColumn;
        this.resetTableStructure();
    }

    updateCollapsedDomains(collapsedDomains) {
        this.definition.collapsedDomains = collapsedDomains;
        this.resetTableStructure();
    }

    getDefinition() {
        return this.definition;
    }

    async load(searchParams) {
        for (const groupBy of [
            ...this.metaData.colGroupBys,
            ...this.metaData.rowGroupBys,
        ]) {
            this._normalize(groupBy);
        }
        if (
            this.metaData.activeMeasures.find(
                (fieldName) =>
                    fieldName !== "__count" && !this.metaData.fields[fieldName],
            )
        ) {
            throw new Error(
                _t(
                    "Some measures are not available: %s",
                    this.metaData.activeMeasures
                        .filter((fieldName) => !this.metaData.fields[fieldName])
                        .join(", "),
                ),
            );
        }
        searchParams.groupBy = [];
        searchParams.orderBy = [];
        await super.load(searchParams);
    }

    /**
     * @param {PivotMeasure} measure
     * @param {PivotDomain} domain
     */
    getPivotCellValue(measure, domain) {
        if (domain.some((node) => node.value === NO_RECORD_AT_THIS_POSITION)) {
            return "";
        }
        const { cols, rows } = this._getColsRowsValuesFromDomain(domain);
        const group = JSON.stringify([rows, cols]);
        const values = this.data.measurements[group];
        const measurementId = this._getAggregateSpec(measure);

        if (values && (values[measurementId] || values[measurementId] === 0)) {
            return values[measurementId];
        }
        return "";
    }

    /**
     * @param {string} groupFieldString
     * @param {string | number | boolean} groupValueString
     * @returns {string | number | boolean}
     */
    getGroupByCellValue(groupFieldString, groupValueString) {
        if (groupValueString === NO_RECORD_AT_THIS_POSITION) {
            return "";
        }
        const { field, granularity, dimensionWithGranularity } =
            this.parseGroupField(groupFieldString);
        const dimension = this.definition.getDimension(dimensionWithGranularity);
        const value = toNormalizedPivotValue(dimension, groupValueString);
        const undef = _t("None");
        if (isDateOrDatetimeField(field)) {
            const adapter = pivotTimeAdapter(granularity);
            return adapter.toValueAndFormat(value, this.getters.getLocale()).value;
        }
        if (field.relation) {
            if (value === false) {
                return undef;
            }
            return this._getRelationalDisplayName(field.relation, value);
        }
        const label = this._displayLabels[field.name]?.[value];
        if (!label) {
            return undef;
        }
        return label;
    }

    /**
     * @param {PivotDomain} domain
     * @returns {string | boolean | number}
     */
    getLastPivotGroupValue(domain) {
        const lastNode = domain.at(-1);
        if (!lastNode) {
            throw new Error("Domain size should be at least 1");
        }
        if (lastNode.field.startsWith("#")) {
            if (
                domain.filter((node) => node.value === NO_RECORD_AT_THIS_POSITION)
                    .length
            ) {
                return NO_RECORD_AT_THIS_POSITION;
            }
            const { dimensionWithGranularity } = this.parseGroupField(lastNode.field);
            const { cols, rows } = this._getColsRowsValuesFromDomain(domain);
            return this._isCol(dimensionWithGranularity) ? cols.at(-1) : rows.at(-1);
        }
        return lastNode.value;
    }

    /** @param {PivotDomain} domain */
    getPivotCellDomain(domain) {
        if (domain.some((node) => node.value === NO_RECORD_AT_THIS_POSITION)) {
            return undefined;
        }
        const { cols, rows } = this._getColsRowsValuesFromDomain(domain);
        const key = JSON.stringify([rows, cols]);
        return this.data.groupDomains[key] || Domain.FALSE.toList();
    }

    resetTableStructure() {
        this._collapsedTableStructure = undefined;
        this._expandedTableStructure = undefined;
    }

    getCollapsedTableStructure() {
        if (this._collapsedTableStructure === undefined) {
            this._collapsedTableStructure = this._buildTableStructure("collapsed");
        }
        return this._collapsedTableStructure;
    }

    getExpandedTableStructure() {
        if (this._expandedTableStructure === undefined) {
            this._expandedTableStructure = this._buildTableStructure("expanded");
        }
        return this._expandedTableStructure;
    }

    /**
     * @param {import("@odoo/o-spreadsheet").PivotDimension} dimension
     * @returns {{ value: string | number | boolean, label: string }[]}
     */
    getPossibleFieldValues(dimension) {
        const valuesWithLabels = [];
        const valuesUniqueness = new Set();
        const isCol = this._isCol(dimension.nameWithGranularity);
        const groupBys = isCol ? this.definition.columns : this.definition.rows;
        const tree = isCol ? this.data.colGroupTree : this.data.rowGroupTree;
        const groupByIndex = groupBys.findIndex(
            (d) => d.nameWithGranularity === dimension.nameWithGranularity,
        );
        const visitTree = (tree) => {
            const { values, labels } = tree.root;
            const value = values[groupByIndex];
            if (value !== undefined && !valuesUniqueness.has(value)) {
                valuesUniqueness.add(value);
                valuesWithLabels.push({
                    value: value,
                    label: labels[groupByIndex].toString(),
                });
            }
            [...tree.directSubTrees.values()].forEach((subTree) => {
                visitTree(subTree);
            });
        };
        visitTree(tree);
        return valuesWithLabels;
    }

    /**
     * @param {"collapsed" | "expanded"} mode
     * @returns {SpreadsheetPivotTable}
     */
    _buildTableStructure(mode) {
        const cols = this._getSpreadsheetCols();
        const rows = this._getSpreadsheetRows(this.data.rowGroupTree);
        rows.push(rows.shift());
        const measures = this.getDefinition()
            .measures.filter((measure) => !measure.isHidden)
            .map((measure) => measure.id);
        /** @type {Record<string, string | undefined>} */
        const fieldsType = {};
        for (const columns of this.getDefinition().columns) {
            fieldsType[columns.fieldName] = columns.type;
        }
        for (const row of this.getDefinition().rows) {
            fieldsType[row.fieldName] = row.type;
        }
        const collapsedDomains =
            mode === "collapsed" ? this.getDefinition().collapsedDomains : undefined;
        return new SpreadsheetPivotTable(
            cols,
            rows,
            measures,
            fieldsType,
            collapsedDomains,
        );
    }

    /**
     * @override
     */
    async _loadData(config) {
        /** @type {(groupFieldString: string) => ReturnType<typeof parseGroupField>} */
        this.parseGroupField = parseGroupField.bind(null, this.metaData.fields);
        const prune = false;
        const loaded = await super._loadData(config, prune);
        if (!loaded) {
            return false;
        }

        const registerLabels = (tree, groupBys) => {
            const group = tree.root;
            if (!tree.directSubTrees.size) {
                for (let i = 0; i < group.values.length; i++) {
                    const { field } = this.parseGroupField(groupBys[i]);
                    if (!field.relation) {
                        this._registerDisplayLabel(
                            field.name,
                            group.values[i],
                            group.labels[i],
                        );
                    } else {
                        const id = group.values[i];
                        const displayName = group.labels[i];
                        this._registerDisplayName(field.relation, id, displayName);
                    }
                }
            }
            [...tree.directSubTrees.values()].forEach((subTree) => {
                registerLabels(subTree, groupBys);
            });
        };

        registerLabels(this.data.colGroupTree, this.metaData.fullColGroupBys);
        registerLabels(this.data.rowGroupTree, this.metaData.fullRowGroupBys);
        return true;
    }

    _registerDisplayLabel(fieldName, value, label) {
        if (!this._displayLabels[fieldName]) {
            this._displayLabels[fieldName] = {};
        }
        this._displayLabels[fieldName][value] = label;
    }

    _registerDisplayName(resModel, resId, displayName) {
        if (!this._displayNames[resModel]) {
            this._displayNames[resModel] = {};
        }
        this._displayNames[resModel][resId] = displayName;
    }

    _getRelationalDisplayName(resModel, resId) {
        const displayName =
            this._displayNames[resModel]?.[resId] ||
            this.serverData.batch.get(
                "mixin.spreadsheet",
                "get_display_names_for_spreadsheet",
                {
                    model: resModel,
                    id: resId,
                },
            );
        if (!displayName) {
            throw new EvaluationError(
                _t("Unable to fetch the label of %(id)s of model %(model)s", {
                    id: resId,
                    model: resModel,
                }),
            );
        }
        return displayName;
    }

    _normalize(groupBy) {
        const [fieldName] = groupBy.split(":");
        const field = this.metaData.fields[fieldName];
        if (!field) {
            throw new EvaluationError(_t("Field %s does not exist", fieldName));
        }
        return super._normalize(groupBy);
    }

    /**
     * @override
     */
    _getGroupValues(group, groupBys) {
        return groupBys.map((gb) => {
            const groupBy = this._normalize(gb);
            const { field, granularity } = this.parseGroupField(gb);
            if (isDateOrDatetimeField(field)) {
                return pivotTimeAdapter(granularity).normalizeServerValue(
                    groupBy,
                    field,
                    group,
                    this.getters.getLocale(),
                );
            }
            return this._sanitizeValue(group[groupBy]);
        });
    }

    /**
     * @override
     */
    _sanitizeLabel(value, groupBy, config) {
        const { metaData } = config;
        const fieldName = groupBy.split(":")[0];
        if (fieldName && metaData.fields[fieldName]) {
            const fields = fieldName.split(".");
            if (fields.length > 1 && fields.at(-1) === "id" && Array.isArray(value)) {
                return value[0];
            }
        }
        return super._sanitizeLabel(value, groupBy, config);
    }

    _isCol(nameWithGranularity) {
        return this.metaData.fullColGroupBys.includes(nameWithGranularity);
    }

    _isRow(nameWithGranularity) {
        return this.metaData.fullRowGroupBys.includes(nameWithGranularity);
    }

    /**
     * @param {string} dimensionWithGranularity
     * @param {unknown} groupValueString
     * @param {(number | boolean | string)[]} rows
     * @param {(number | boolean | string)[]} cols
     * @private
     * @returns {number | boolean | string}
     */
    _parsePivotFormulaWithPosition(
        dimensionWithGranularity,
        groupValueString,
        cols,
        rows,
    ) {
        const position = toNumber(groupValueString, DEFAULT_LOCALE) - 1;
        const table = this.getExpandedTableStructure();
        let tree;
        if (this._isCol(dimensionWithGranularity)) {
            tree = table.getColTree();
            for (const col of cols) {
                tree = tree && tree.find((child) => child.value === col)?.children;
            }
        } else {
            tree = table.getRowTree();
            for (const row of rows) {
                tree = tree && tree.find((child) => child.value === row)?.children;
            }
        }
        if (tree) {
            const value = tree[position]?.value;
            return value !== undefined ? value : NO_RECORD_AT_THIS_POSITION;
        }
        return NO_RECORD_AT_THIS_POSITION;
    }

    /**
     * @param {PivotDomain} domain
     * @private
     */
    _getColsRowsValuesFromDomain(domain) {
        const rows = [];
        const cols = [];
        for (const node of domain) {
            const { isPositional, dimensionWithGranularity } = this.parseGroupField(
                node.field,
            );
            let value;
            if (isPositional) {
                value = this._parsePivotFormulaWithPosition(
                    dimensionWithGranularity,
                    node.value,
                    cols,
                    rows,
                );
            } else {
                const dimension = this.definition.getDimension(
                    dimensionWithGranularity,
                );
                value = toNormalizedPivotValue(dimension, node.value);
            }
            if (this._isCol(dimensionWithGranularity)) {
                cols.push(value);
            } else if (this._isRow(dimensionWithGranularity)) {
                rows.push(value);
            } else {
                throw new EvaluationError(
                    _t("Dimension %s is not a group by", dimensionWithGranularity),
                );
            }
        }
        return { rows, cols };
    }

    /** @returns {PivotTableRow[]} */
    _getSpreadsheetRows(tree) {
        /**@type {PivotTableRow[]}*/
        const rows = [];
        const group = tree.root;
        const indent = group.labels.length;
        const rowGroupBys = this.metaData.fullRowGroupBys;

        rows.push({
            fields: rowGroupBys.slice(0, indent),
            values: group.values.map((val) => val),
            indent,
        });

        const subTreeKeys = tree.sortedKeys || [...tree.directSubTrees.keys()];
        subTreeKeys.forEach((subTreeKey) => {
            const subTree = tree.directSubTrees.get(subTreeKey);
            rows.push(...this._getSpreadsheetRows(subTree));
        });
        return rows;
    }

    /** @returns {PivotTableColumn[][]} */
    _getSpreadsheetCols() {
        const colGroupBys = this.metaData.fullColGroupBys;
        const height = colGroupBys.length;
        const measures = this.getDefinition().measures.filter(
            (measure) => !measure.isHidden,
        );
        const measureCount = measures.length;
        const leafCounts = getLeafCounts(this.data.colGroupTree);

        const headers = new Array(height).fill(0).map(() => []);

        function generateTreeHeaders(tree) {
            const group = tree.root;
            const rowIndex = group.values.length;
            if (rowIndex !== 0) {
                const row = headers[rowIndex - 1];
                const leafCount = leafCounts[JSON.stringify(tree.root.values)];
                const cell = {
                    fields: colGroupBys.slice(0, rowIndex),
                    values: group.values.map((val) => val),
                    width: leafCount * measureCount,
                };
                row.push(cell);
            }

            [...tree.directSubTrees.values()].forEach((subTree) => {
                generateTreeHeaders(subTree);
            });
        }

        generateTreeHeaders(this.data.colGroupTree);
        const hasColGroupBys = this.metaData.colGroupBys.length;

        const measureRow = [];

        if (hasColGroupBys) {
            headers[headers.length - 1].forEach((cell) => {
                measures.forEach((measure) => {
                    const measureCell = {
                        fields: [...cell.fields, "measure"],
                        values: [...cell.values, measure.id],
                        width: 1,
                    };
                    measureRow.push(measureCell);
                });
            });
        }
        measures.forEach((measure) => {
            const measureCell = {
                fields: ["measure"],
                values: [measure.id],
                width: 1,
            };
            measureRow.push(measureCell);
        });
        headers.push(measureRow);
        if (headers.length === 1) {
            headers.unshift([]);
        }
        headers[headers.length - 2].push({
            fields: [],
            values: [],
            width: measures.length,
        });

        return headers;
    }

    _getAggregateSpec(measure) {
        if (measure.fieldName === "__count") {
            return "__count";
        }
        if (measure.aggregator) {
            return `${measure.fieldName}:${measure.aggregator}`;
        }
        if (measure.type === "many2one") {
            return `${measure.fieldName}:count_distinct`;
        }
        const field = this.metaData.fields[measure.fieldName];
        if (!field.aggregator) {
            throw new Error(
                `Field ${measure.fieldName} doesn't have a default aggregator`,
            );
        }
        return `${measure.fieldName}:${field.aggregator}`;
    }

    /**
     * @override
     * @protected
     * @return {string[]}
     */
    _getMeasureSpecs() {
        return this.getDefinition()
            .measures.filter((measure) => !measure.computedBy)
            .map(this._getAggregateSpec, this);
    }

    /** @override */
    async _getGroupsSubdivision(params, groupInfo) {
        const customFields = this.definition.customFields || {};

        const { columns, rows } = this.getDefinition();
        const allGroupBys = params.groupingSets.flat();
        const order = columns
            .concat(rows)
            .filter((dimension) => allGroupBys.includes(dimension.nameWithGranularity))
            .map((dimension) =>
                dimension.order
                    ? `${dimension.nameWithGranularity} ${dimension.order}`
                    : dimension.nameWithGranularity,
            )
            .join(",");
        params.kwargs.order = order;

        const hasCustomField = allGroupBys.some((gb) => customFields[gb] !== undefined);
        if (!hasCustomField) {
            return await super._getGroupsSubdivision(params, groupInfo);
        } else if (
            params.measureSpecs.some((measure) => measure.endsWith(":count_distinct"))
        ) {
            throw new Error(
                _t('Cannot use custom pivot groups with "Count Distinct" measure'),
            );
        } else {
            return this._doCustomGroupSubdivision(params, groupInfo);
        }
    }

    _aggregateSubGroups(subGroups, measures) {
        if (subGroups.length === 1) {
            return subGroups[0];
        }
        const subGroup = { ...subGroups[0] };
        for (const measure of measures) {
            const aggregator = measure.split(":")[1];
            switch (aggregator) {
                case "sum":
                case "count":
                    subGroup[measure] = subGroups.reduce(
                        (sum, sg) => sum + sg[measure],
                        0,
                    );
                    break;
                case "min":
                    subGroup[measure] = Math.min(...subGroups.map((sg) => sg[measure]));
                    break;
                case "max":
                    subGroup[measure] = Math.max(...subGroups.map((sg) => sg[measure]));
                    break;
                case "avg": {
                    const totalCount = subGroups.reduce(
                        (sum, sg) => sum + (sg.__count || 0),
                        0,
                    );
                    if (totalCount === 0) {
                        subGroup[measure] = 0;
                    } else {
                        subGroup[measure] =
                            subGroups.reduce(
                                (sum, sg) => sum + sg[measure] * sg.__count,
                                0,
                            ) / totalCount;
                    }
                    break;
                }
            }
        }
        subGroup.__count = subGroups.reduce((sum, sg) => sum + (sg.__count || 0), 0);

        const domains = subGroups.map((sg) => sg.__domain || []);
        subGroup.__domain = Domain.combine(domains, "OR").toList();
        const extraDomains = subGroups.map((sg) => sg.__extraDomain || []);
        subGroup.__extraDomain = Domain.combine(extraDomains, "OR").toList();

        return subGroup;
    }

    _sortCustomFieldsInSubGroups(groupBys, subGroups) {
        const isInOthersGroup = (subGroup, groupBy, customField) => {
            const value = Array.isArray(subGroup[groupBy])
                ? subGroup[groupBy][0]
                : subGroup[groupBy];
            const otherGroup = customField.groups.find((g) => g.isOtherGroup);
            return otherGroup && value === otherGroup.name;
        };

        const sortFn = (subGroupA, subGroupB, order, groupBy, customField) => {
            if (isInOthersGroup(subGroupB, groupBy, customField)) {
                return -1;
            }
            if (isInOthersGroup(subGroupA, groupBy, customField)) {
                return 1;
            }
            const aValue = subGroupA[groupBy];
            const bValue = subGroupB[groupBy];
            if (aValue === false) {
                return order === "asc" ? 1 : -1;
            } else if (bValue === false) {
                return order === "asc" ? -1 : 1;
            }

            const aLabel = (
                Array.isArray(aValue) ? aValue[1] : String(aValue)
            ).toLowerCase();
            const bLabel = (
                Array.isArray(bValue) ? bValue[1] : String(bValue)
            ).toLowerCase();
            return order === "asc"
                ? aLabel.localeCompare(bLabel)
                : bLabel.localeCompare(aLabel);
        };

        const sortSubGroups = (groupBys, subGroups) => {
            const groupBy = groupBys[0];
            const childrenMap = new Map();

            for (const item of subGroups) {
                const value = item[groupBy];
                const key = Array.isArray(value) ? value[0] : value;
                if (!childrenMap.has(key)) {
                    childrenMap.set(key, []);
                }
                childrenMap.get(key).push(item);
            }

            const customField = this.definition.customFields?.[groupBy];
            const keys = Array.from(childrenMap.keys());
            const order = this.definition.getDimension(groupBy)?.order;

            if (customField && order) {
                keys.sort((a, b) => {
                    const subGroupB = childrenMap.get(b)[0];
                    const subGroupA = childrenMap.get(a)[0];
                    return sortFn(subGroupA, subGroupB, order, groupBy, customField);
                });
            }

            return keys.flatMap((key) =>
                groupBys.length > 1
                    ? sortSubGroups(groupBys.slice(1), childrenMap.get(key))
                    : childrenMap.get(key),
            );
        };

        return sortSubGroups(groupBys, subGroups);
    }

    async _doCustomGroupSubdivision(params, groupInfo) {
        const customFields = this.definition.customFields || {};

        const mockGroupInfo = groupInfo.map((info) => ({
            ...info,
            rowGroupBy: info.rowGroupBy.map(
                (gb) => customFields[gb]?.parentField || gb,
            ),
            colGroupBy: info.colGroupBy.map(
                (gb) => customFields[gb]?.parentField || gb,
            ),
        }));

        const groupInfoKeysSet = new Set();
        const uniqueGroupInfo = [];
        for (const info of mockGroupInfo) {
            const { rowGroupBy, colGroupBy } = info;
            const uniqueGroups = [
                ...new Set([...rowGroupBy, ...colGroupBy].sort()),
            ].join(",");
            if (!groupInfoKeysSet.has(uniqueGroups)) {
                uniqueGroupInfo.push({
                    ...info,
                    rowGroupBy,
                    colGroupBy,
                    subGroupIndex: groupInfoKeysSet.size,
                });
                groupInfoKeysSet.add(uniqueGroups);
            }
        }
        const uniqueGroupingSets = [...groupInfoKeysSet].map((key) =>
            key.split(",").filter((gb) => gb !== ""),
        );

        if (params.kwargs.order) {
            const fieldNameRegex = /(.*) (asc|desc)/;
            params.kwargs.order = params.kwargs.order
                .split(",")
                .filter((part) => {
                    const groupBy = part.match(fieldNameRegex)?.[1];
                    return customFields[groupBy] === undefined;
                })
                .join(",");
        }

        const result = await super._getGroupsSubdivision(
            { ...params, groupingSets: uniqueGroupingSets },
            uniqueGroupInfo,
        );

        const resultWithCustomGroups = [];
        for (let i = 0; i < groupInfo.length; i++) {
            const info = groupInfo[i];
            const mockInfo = mockGroupInfo[i];
            const mockGroupBys = [
                ...new Set([...mockInfo.rowGroupBy, ...mockInfo.colGroupBy].sort()),
            ];
            const resultIndex = uniqueGroupingSets.findIndex((groups) =>
                deepEquals(groups, mockGroupBys),
            );
            const subGroups = result[resultIndex].subGroups;

            const groupBys = [...info.rowGroupBy, ...info.colGroupBy];
            const hasCustomField = groupBys.some(
                (gb) => customFields[gb] !== undefined,
            );
            if (hasCustomField) {
                resultWithCustomGroups.push(
                    this._addCustomGroupsToGroup(params, info, subGroups),
                );
            } else {
                resultWithCustomGroups.push({ ...info, subGroups });
            }
        }
        return resultWithCustomGroups;
    }

    _addCustomGroupsToGroup(params, groupInfo, subGroups) {
        const customFields = this.definition.customFields || {};
        const { rowGroupBy, colGroupBy } = groupInfo;
        const groupBys = [...rowGroupBy, ...colGroupBy];

        for (const groupBy of groupBys) {
            const customField = customFields[groupBy];
            if (!customField) {
                continue;
            }

            for (const subGroup of subGroups) {
                const parentFieldName = customField.parentField;
                const parentValue = Array.isArray(subGroup[parentFieldName])
                    ? subGroup[parentFieldName][0]
                    : subGroup[parentFieldName];
                const group =
                    customField.groups.find((g) => g.values.includes(parentValue)) ||
                    customField.groups.find((g) => g.isOtherGroup);

                subGroup[groupBy] = group ? group.name : subGroup[parentFieldName];
            }
        }

        const getKey = (subGroup) =>
            JSON.stringify(groupBys.map((groupBy) => subGroup[groupBy]));
        const groupedSubgroups = Object.groupBy(subGroups, getKey);

        const aggregatedSubgroups = Object.values(groupedSubgroups).map((subGroups) =>
            this._aggregateSubGroups(subGroups, params.measureSpecs),
        );
        const sortedSubGroups = this._sortCustomFieldsInSubGroups(
            groupBys,
            aggregatedSubgroups,
        );

        return { ...groupInfo, subGroups: sortedSubGroups };
    }

    /** @override */
    _getMeasurements(group) {
        return this.getDefinition()
            .measures.filter((measure) => !measure.computedBy)
            .reduce((measurements, measure) => {
                const measurementId = this._getAggregateSpec(measure);
                let measurement = group[measurementId];
                if (measurement instanceof Array) {
                    measurement = 1;
                }
                if (measure.type === "boolean" && typeof measurement === "boolean") {
                    measurement = measurement ? 1 : 0;
                }
                measurements[measurementId] = measurement;
                return measurements;
            }, {});
    }

    /** @override */
    _getCellValue(groupId, measureName, config) {
        const measure = this.getDefinition().measures.find(
            (m) => m.fieldName === measureName,
        );
        const measurementId = this._getAggregateSpec(measure);
        const key = JSON.stringify(groupId);
        if (!config.data.measurements[key]) {
            return;
        }
        return config.data.measurements[key][measurementId];
    }
}
