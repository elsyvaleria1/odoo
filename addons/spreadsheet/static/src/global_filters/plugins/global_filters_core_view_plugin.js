/** @odoo-module native */
/** @ts-check */

/**
 * @typedef {import("@spreadsheet").GlobalFilter} GlobalFilter
 * @typedef {import("@spreadsheet").FieldMatching} FieldMatching
 * @typedef {import("@spreadsheet").DateGlobalFilter} DateGlobalFilter
 * @typedef {import("@spreadsheet").RelationalGlobalFilter} RelationalGlobalFilter
 * @typedef {import("@spreadsheet").DateValue} DateValue
 * @typedef {import("@spreadsheet").DateDefaultValue} DateDefaultValue
 */

import { EvaluationError, helpers } from "@odoo/o-spreadsheet";
import {
    checkFilterValueIsValid,
    getDateDomain,
    getDateRange,
} from "@spreadsheet/global_filters/helpers";
import { CommandResult } from "@spreadsheet/o_spreadsheet/cancelled_reason";
import { OdooCoreViewPlugin } from "@spreadsheet/plugins";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";
import { now, serializeDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { deepEqual } from "@web/core/utils/collections/objects";

import { getItemId } from "../../helpers/model.js";
import { getFilterCellValue, getFilterValueDomain } from "../helpers.js";

const log = makeLogger("spreadsheet.global_filters");

const { UuidGenerator, createEmptyExcelSheet, createEmptySheet, toXC, toNumber } =
    helpers;
const uuidGenerator = new UuidGenerator();

export class GlobalFiltersCoreViewPlugin extends OdooCoreViewPlugin {
    static getters = /** @type {const} */ ([
        "exportSheetWithActiveFilters",
        "getFilterDisplayValue",
        "getGlobalFilterByName",
        "getGlobalFilterDomain",
        "getGlobalFilterValue",
        "getActiveFilterCount",
        "isGlobalFilterActive",
        "getTextFilterOptions",
        "getTextFilterOptionsFromRanges",
    ]);
    constructor(config) {
        super(config);
        this.values = {};
    }

    /** @param {import("@spreadsheet").AllCommand} cmd */
    allowDispatch(cmd) {
        switch (cmd.type) {
            case "SET_GLOBAL_FILTER_VALUE": {
                const filter = this.getters.getGlobalFilter(cmd.id);
                if (!filter) {
                    log.logic("setValue:rejected", {
                        id: cmd.id,
                        reason: "FilterNotFound",
                    });
                    return CommandResult.FilterNotFound;
                }
                if (!checkFilterValueIsValid(filter, cmd.value)) {
                    log.logic("setValue:rejected", () => ({
                        id: cmd.id,
                        type: filter.type,
                        reason: "InvalidValueTypeCombination",
                        value: cmd.value,
                    }));
                    return CommandResult.InvalidValueTypeCombination;
                }

                const currentFilterValue = this.getters.getGlobalFilterValue(cmd.id);
                if (deepEqual(currentFilterValue, cmd.value)) {
                    return CommandResult.NoChanges;
                }
                break;
            }
        }
        return CommandResult.Success;
    }

    /** @param {import("@spreadsheet").AllCommand} cmd */
    handle(cmd) {
        switch (cmd.type) {
            case "SET_GLOBAL_FILTER_VALUE":
                log.logic("setValue", () => ({
                    id: cmd.id,
                    cleared: cmd.value === undefined,
                    value: cmd.value,
                }));
                if (cmd.value === undefined) {
                    this._clearGlobalFilterValue(cmd.id);
                } else {
                    this._setGlobalFilterValue(cmd.id, cmd.value);
                }
                break;
            case "REMOVE_GLOBAL_FILTER":
                delete this.values[cmd.id];
                break;
        }
    }

    /**
     * @param {string} filterId
     * @param {FieldMatching} fieldMatching
     * @return {Domain}
     */
    getGlobalFilterDomain(filterId, fieldMatching) {
        /** @type {GlobalFilter} */
        const filter = this.getters.getGlobalFilter(filterId);
        if (!filter) {
            return new Domain();
        }
        const value = this.getGlobalFilterValue(filter.id);
        const field = fieldMatching.chain;
        if (!field || !value) {
            return new Domain();
        }
        const domain =
            filter.type === "date"
                ? this._getDateDomain(filter, fieldMatching)
                : getFilterValueDomain(filter, value, field);
        log.pipeline("domain", () => ({
            filterId,
            type: filter.type,
            field,
            domain: domain.toString(),
        }));
        return domain;
    }

    /**
     * @param {string} filterId
     * @returns {string|Array<string>|Object}
     */
    getGlobalFilterValue(filterId) {
        const filter = this.getters.getGlobalFilter(filterId);

        const value = filterId in this.values ? this.values[filterId].value : undefined;
        if (value !== undefined) {
            return value;
        }
        const preventDefaultValue = this.values[filterId]?.preventDefaultValue;
        if (preventDefaultValue || filter.defaultValue === undefined) {
            return undefined;
        }
        switch (filter.type) {
            case "date":
                return this._getDateValueFromDefaultValue(filter.defaultValue);
            case "relation":
                if (filter.defaultValue.ids === "current_user") {
                    return { ...filter.defaultValue, ids: [user.userId] };
                }
                return filter.defaultValue;
            default:
                return filter.defaultValue;
        }
    }

    /**
     * @param {string} id
     * @returns { boolean }
     */
    isGlobalFilterActive(id) {
        return this.getGlobalFilterValue(id) !== undefined;
    }

    /** @returns {number} */
    getActiveFilterCount() {
        return this.getters
            .getGlobalFilters()
            .filter((filter) => this.isGlobalFilterActive(filter.id)).length;
    }

    getFilterDisplayValue(filterName) {
        const filter = this.getGlobalFilterByName(filterName);
        if (!filter) {
            throw new EvaluationError(
                _t(`Filter "%(filter_name)s" not found`, { filter_name: filterName }),
            );
        }
        switch (filter.type) {
            case "date":
                return this._getDateFilterDisplayValue(filter);
            default: {
                const value = this.getGlobalFilterValue(filter.id);
                if (!value) {
                    return [[{ value: "" }]];
                }
                return getFilterCellValue(this.getters, filter, value);
            }
        }
    }

    /**
     * @param {string} filterId
     * @returns {{value: string, formattedValue: string}[]}
     */
    getTextFilterOptions(filterId) {
        const filter = this.getters.getGlobalFilter(filterId);
        if (filter.type !== "text" || !filter.rangesOfAllowedValues) {
            return [];
        }
        const additionOptions = [
            ...(this.getGlobalFilterValue(filterId)?.strings ?? []),
            ...(filter.defaultValue?.strings ?? []),
        ];
        const options = this.getTextFilterOptionsFromRanges(
            filter.rangesOfAllowedValues,
            additionOptions,
        );
        return options;
    }

    /**
     * @param {object[]} ranges
     * @param {string[]} additionalOptionValues
     */
    getTextFilterOptionsFromRanges(ranges, additionalOptionValues = []) {
        const cells = ranges.flatMap((range) =>
            this.getters.getEvaluatedCellsInZone(range.sheetId, range.zone),
        );
        const uniqueFormattedValues = new Set();
        const uniqueValues = new Set();
        const allowedValues = cells
            .filter(
                (cell) => !["empty", "error"].includes(cell.type) && cell.value !== "",
            )
            .map((cell) => ({
                value: cell.value.toString(),
                formattedValue: cell.formattedValue,
            }))
            .filter((cell) => {
                if (uniqueFormattedValues.has(cell.formattedValue)) {
                    return false;
                }
                uniqueFormattedValues.add(cell.formattedValue);
                uniqueValues.add(cell.value);
                return true;
            });
        const additionalOptions = additionalOptionValues
            .map((value) => ({ value, formattedValue: value }))
            .filter((cell) => {
                if (
                    cell.value === undefined ||
                    cell.value === "" ||
                    uniqueValues.has(cell.value)
                ) {
                    return false;
                }
                uniqueValues.add(cell.value);
                return true;
            });
        return allowedValues.concat(additionalOptions);
    }

    /**
     * @param {string} id
     * @param {string|Array<string>|Object} value
     */
    _setGlobalFilterValue(id, value) {
        this.values[id] = {
            preventDefaultValue: false,
            value,
        };
    }

    /** @param {string} id */
    _clearGlobalFilterValue(id) {
        this.values[id] = {
            preventDefaultValue: true,
            value: undefined,
        };
    }

    /**
     * @param {string} label
     * @returns {GlobalFilter|undefined}
     */
    getGlobalFilterByName(label) {
        return this.getters
            .getGlobalFilters()
            .find(
                (filter) =>
                    this.getters.dynamicTranslate(filter.label) ===
                    this.getters.dynamicTranslate(label),
            );
    }

    _getDateFilterDisplayValue(filter) {
        const { from, to } = getDateRange(this.getGlobalFilterValue(filter.id));
        const locale = this.getters.getLocale();
        const _from = {
            value: from ? toNumber(serializeDate(from), locale) : "",
            format: locale.dateFormat,
        };
        const _to = {
            value: to ? toNumber(serializeDate(to), locale) : "",
            format: locale.dateFormat,
        };
        return [[_from], [_to]];
    }

    /**
     * @param {DateDefaultValue} defaultValue
     * @returns {DateValue|undefined}
     */
    _getDateValueFromDefaultValue(defaultValue) {
        const year = now().year;
        switch (defaultValue) {
            case "this_year":
                return { type: "year", year };
            case "this_month": {
                const month = now().month;
                return { type: "month", year, month };
            }
            case "this_quarter": {
                const quarter = Math.ceil(now().month / 3);
                return { type: "quarter", year, quarter };
            }
            case "today":
            case "yesterday":
            case "last_7_days":
            case "last_30_days":
            case "last_90_days":
            case "month_to_date":
            case "last_month":
            case "last_12_months":
            case "year_to_date":
                return {
                    type: "relative",
                    period: defaultValue,
                };
        }
        return undefined;
    }

    /**
     * @private
     * @param {DateGlobalFilter} filter
     * @param {FieldMatching} fieldMatching
     * @returns {Domain}
     */
    _getDateDomain(filter, fieldMatching) {
        if (!fieldMatching.chain) {
            return new Domain();
        }
        const field = fieldMatching.chain;
        const type = /** @type {"date" | "datetime"} */ (fieldMatching.type);
        const offset = fieldMatching.offset || 0;
        const { from, to } = getDateRange(this.getGlobalFilterValue(filter.id), offset);
        return getDateDomain(from, to, field, type);
    }

    /** @param {Object} data */
    exportForExcel(data) {
        if (this.getters.getGlobalFilters().length === 0) {
            return;
        }
        this.exportSheetWithActiveFilters(data);
        data.sheets[data.sheets.length - 1] = {
            ...createEmptyExcelSheet(uuidGenerator.smallUuid(), _t("Active Filters")),
            ...data.sheets.at(-1),
        };
    }

    exportSheetWithActiveFilters(data) {
        if (this.getters.getGlobalFilters().length === 0) {
            return;
        }

        const cells = {
            A1: "Filter",
            B1: "Value",
        };
        const formats = {};
        let numberOfCols = 2;
        let filterRowIndex = 1;
        for (const filter of this.getters.getGlobalFilters()) {
            cells[`A${filterRowIndex + 1}`] = filter.label;
            const result = this.getFilterDisplayValue(filter.label);
            for (const colIndex in result) {
                numberOfCols = Math.max(numberOfCols, Number(colIndex) + 2);
                for (const rowIndex in result[colIndex]) {
                    const cell = result[colIndex][rowIndex];
                    if (cell.value === undefined) {
                        continue;
                    }
                    const xc = toXC(
                        Number(colIndex) + 1,
                        Number(rowIndex) + filterRowIndex,
                    );
                    cells[xc] = cell.value.toString();
                    if (cell.format) {
                        const formatId = getItemId(cell.format, data.formats);
                        formats[xc] = formatId;
                    }
                }
            }
            filterRowIndex += result[0].length;
        }
        const styleId = getItemId({ bold: true }, data.styles);

        const sheet = {
            ...createEmptySheet(uuidGenerator.smallUuid(), _t("Active Filters")),
            cells,
            formats,
            styles: {
                A1: styleId,
                B1: styleId,
            },
            colNumber: numberOfCols,
            rowNumber: filterRowIndex,
        };
        data.sheets.push(sheet);
    }
}
