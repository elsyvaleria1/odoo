// @ts-check
/** @odoo-module native */

/** @typedef {import("@web/views/list/list_column_utils").Column} Column */

import { AGGREGATABLE_FIELD_TYPES } from "@web/model/relational_model";

/**
 * @typedef {{
 * nameColspan: number,
 * aggregateColumns: Column[],
 * pagerColspan: number,
 * }} AggregateLayout
 */

/**
 * @param {Column} column
 * @param {Record<string, any>} fields
 * @param {Record<string, any>} aggregates
 * @returns {boolean}
 */
function isAggregateColumn(column, fields, aggregates) {
    return (
        column.name in aggregates &&
        column.widget !== "handle" &&
        AGGREGATABLE_FIELD_TYPES.includes(fields[column.name].type)
    );
}

/**
 * @param {Column[]} columns
 * @param {Record<string, any>} fields
 * @param {Record<string, any>} aggregates
 * @param {{ hasSelectors?: boolean, hasOpenFormViewColumn?: boolean }} [options]
 * @returns {AggregateLayout}
 */
export function getAggregateLayout(
    columns,
    fields,
    aggregates,
    { hasSelectors, hasOpenFormViewColumn } = {},
) {
    let firstIndex = -1;
    let lastIndex = -1;
    columns.forEach((column, index) => {
        if (isAggregateColumn(column, fields, aggregates)) {
            if (firstIndex === -1) {
                firstIndex = index;
            }
            lastIndex = index;
        }
    });
    const hasAggregate = firstIndex > -1;
    return {
        nameColspan:
            (hasAggregate ? firstIndex : columns.length) + (hasSelectors ? 1 : 0),
        aggregateColumns: hasAggregate ? columns.slice(firstIndex, lastIndex + 1) : [],
        pagerColspan:
            (hasAggregate ? columns.length - lastIndex - 1 : 0) +
            (hasOpenFormViewColumn ? 1 : 0),
    };
}
