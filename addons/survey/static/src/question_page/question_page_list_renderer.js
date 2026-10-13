/** @odoo-module native */
import { makeContext } from "@web/core/context";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { ListRenderer } from "@web/views/list";
import { layoutSectionColumns } from "@web/views/section_list/section_list_renderer";

export class QuestionPageListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.ui = useService("ui");

        this.discriminant = "is_page";
        this.fieldsToShow = ["random_questions_count"];
        this.titleField = "title";

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

    getCellClass(column, record) {
        const classNames = super.getCellClass(column, record);
        if (column.type === "button_group") {
            return `${classNames} text-end`;
        }
        return classNames;
    }

    isSectionColumnKept(column, index, titleIndex) {
        return (
            index < titleIndex ||
            column.type !== "field" ||
            column.widget === "handle" ||
            this.fieldsToShow.includes(column.name)
        );
    }

    getSectionColumns(columns) {
        return layoutSectionColumns(columns, {
            isKept: (column, index, titleIndex) =>
                this.isSectionColumnKept(column, index, titleIndex),
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

    /** @override */
    focusCell(column, forward = true) {
        const actualColumn = column.name
            ? this.columns.find((col) => col.name === column.name)
            : column;
        super.focusCell(actualColumn, forward);
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

    /**
     * @override
     * @param record
     * @return {Promise<void>}
     */
    async onDeleteRecord(record) {
        const triggeredRecords = this.props.list.records.filter((rec) =>
            rec.data.triggering_question_ids.currentIds.includes(record.resId),
        );
        if (triggeredRecords.length) {
            const res = await super.onDeleteRecord(record);
            await this.props.list.model.root.save();
            return res;
        } else {
            return super.onDeleteRecord(record);
        }
    }
}
