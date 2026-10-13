// @ts-check
/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { ListRenderer } from "@web/views/list";

/**
 * @typedef {import("@web/model/relational_model/record").RelationalRecord} RelationalRecord
 * @typedef {import("@web/views/list/list_column_utils").Column} Column
 * @typedef {(column: Column, index: number, titleIndex: number) => boolean} SectionColumnPolicy
 */

const log = makeLogger("web.section_list");

/**
 * @param {Column} column
 * @returns {Column}
 */
export function emptySectionCell(column) {
    return column.type === "field"
        ? { ...column, invisible: "True" }
        : { ...column, type: "button_group", buttons: [] };
}

/**
 * @param {Column[]} columns
 * @param {{
 *   isKept: SectionColumnPolicy,
 *   titleField: string,
 *   allColumns?: Column[],
 *   emptyCell?: (column: Column) => Column,
 *   owner?: string,
 * }} policy
 * @returns {Column[]}
 */
export function layoutSectionColumns(
    columns,
    { isKept, titleField, allColumns = [], emptyCell = emptySectionCell, owner = "" },
) {
    /** @param {Column} col */
    const isTitle = (col) => col.type === "field" && col.name === titleField;
    const shownTitleIndex = columns.findIndex(isTitle);
    const kept = columns.map(
        (col, index) =>
            index !== shownTitleIndex && isKept(col, index, shownTitleIndex),
    );
    let titleIndex = shownTitleIndex;
    let titleColumn = columns[titleIndex];
    if (titleIndex < 0) {
        titleIndex = kept.indexOf(false);
        titleColumn = titleIndex < 0 ? undefined : allColumns.find(isTitle);
    }
    let start = titleIndex;
    let end = titleIndex;
    if (titleColumn) {
        while (start > 0 && !kept[start - 1]) {
            start--;
        }
        while (end < columns.length - 1 && !kept[end + 1]) {
            end++;
        }
    }
    /** @type {Column[]} */
    const sectionColumns = [];
    /** @type {string[]} */
    const emptied = [];
    for (let index = 0; index < columns.length; index++) {
        if (titleColumn && index === start) {
            sectionColumns.push({ ...titleColumn, colspan: end - start + 1 });
            index = end;
        } else if (kept[index]) {
            sectionColumns.push({ ...columns[index] });
        } else {
            emptied.push(columns[index].name ?? columns[index].id);
            sectionColumns.push(emptyCell(columns[index]));
        }
    }
    log.logic("sectionColumns", () => ({
        owner,
        titleShown: shownTitleIndex >= 0,
        titleSpan: titleColumn ? `${start}-${end}` : "none",
        kept: columns
            .filter((_col, index) => kept[index])
            .map((col) => col.name ?? col.id)
            .join(","),
        emptied: emptied.join(","),
    }));
    return sectionColumns;
}

export class SectionListRenderer extends ListRenderer {
    setup() {
        super.setup();

        this.displayType = "line_section";

        this.titleField = "display_name";

        useLayoutEffect(
            (table) => {
                if (table) {
                    table.classList.add("o_section_list_view");
                }
            },
            () => [this.tableRef.el],
        );
    }

    /** @param {RelationalRecord} record */
    getColumns(record) {
        const columns = super.getColumns(record);
        if (this.isSection(record)) {
            return this.getSectionColumns(columns, record);
        }
        return columns;
    }

    /** @param {RelationalRecord} record */
    getRowClass(record) {
        const classNames = super.getRowClass(record).split(" ");
        if (this.isSection(record)) {
            classNames.push(`o_is_${this.displayType}`, `fw-bold`);
        }
        return classNames.join(" ");
    }

    /**
     * @param {Column} column
     * @param {RelationalRecord} _record
     * @param {number} _index
     * @param {number} _titleIndex
     */
    isSectionColumnKept(column, _record, _index, _titleIndex) {
        return column.widget === "handle";
    }

    /**
     * @param {Column[]} columns
     * @param {RelationalRecord} record
     */
    getSectionColumns(columns, record) {
        if (!this.allColumns.some((col) => col.name === this.titleField)) {
            throw new Error(
                `${this.constructor.name}: no column named "${this.titleField}" in the list; ` +
                    `a section row has no label to render.`,
            );
        }
        return layoutSectionColumns(columns, {
            isKept: (column, index, titleIndex) =>
                this.isSectionColumnKept(column, record, index, titleIndex),
            titleField: this.titleField,
            allColumns: this.allColumns,
            owner: this.constructor.name,
        });
    }

    /** @param {RelationalRecord} record */
    displayDeleteIcon(record) {
        return !this.isSection(record) && super.displayDeleteIcon(record);
    }

    /** @param {RelationalRecord} record */
    isSection(record) {
        return record.data.display_type === this.displayType;
    }
}
