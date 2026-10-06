/** @odoo-module native */
import { makeContext } from "@web/core/context";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { ListRenderer } from "@web/views/list";
import { layoutSectionColumns } from "@web/views/section_list/section_list_renderer";

export class SlideCategoryListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.ui = useService("ui");

        this.discriminant = "is_category";
        this.titleField = "name";

        useLayoutEffect(
            (table) => {
                if (table) {
                    table.classList.add("o_section_list_view");
                }
            },
            () => [this.tableRef.el],
        );
    }

    add(params) {
        let editable = false;
        if (params.context && !this.ui.isSmall) {
            const evaluatedContext = makeContext([params.context]);
            if (evaluatedContext[`default_${this.discriminant}`]) {
                editable = this.props.editable;
            }
        }
        super.add({ ...params, editable });
    }

    getColumns(record) {
        const columns = super.getColumns(record);
        if (this.isSection(record)) {
            return this.getSectionColumns(columns);
        }
        return columns;
    }

    getRowClass(record) {
        const classNames = super.getRowClass(record).split(" ");
        if (this.isSection(record)) {
            classNames.push(`o_is_section`, `fw-bold`);
        }
        return classNames.join(" ");
    }

    isSectionColumnKept(column) {
        return column.widget === "handle";
    }

    getSectionColumns(columns) {
        return layoutSectionColumns(columns, {
            isKept: (column) => this.isSectionColumnKept(column),
            titleField: this.titleField,
            allColumns: this.allColumns,
            owner: this.constructor.name,
        });
    }

    isInlineEditable(record) {
        return this.isSection(record) && this.props.editable;
    }

    isSection(record) {
        return record.data[this.discriminant];
    }

    onCellKeydownEditMode(hotkey) {
        switch (hotkey) {
            case "enter":
            case "tab":
            case "shift+tab": {
                this.props.list.leaveEditMode();
                return true;
            }
        }
        return super.onCellKeydownEditMode(...arguments);
    }
}
