/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { ListRenderer } from "@web/views/list";

const log = makeLogger("hr_skills.skills_list");

export class CommonSkillsListRenderer extends ListRenderer {
    get colspan() {
        const colspan = this.nbCols;
        log.logic("groupColspan", () => ({
            renderer: this.constructor.name,
            colspan,
            columns: this.columns.length,
            allColumns: this.allColumns.length,
            hasActionsColumn: this.hasActionsColumn,
        }));
        return colspan;
    }

    get groupBy() {
        return "";
    }

    groupedList(list) {
        const grouped = {};

        for (const record of list.records) {
            const group = record.data[this.groupBy];
            const key = group ? group.id : 0;

            if (grouped[key] === undefined) {
                grouped[key] = {
                    id: group ? group.id : false,
                    name: (group && group.display_name) || _t("Other"),
                    list: {
                        records: [],
                    },
                };
            }

            grouped[key].list.records.push(record);
        }
        return grouped;
    }

    get showTable() {
        return this.props.list.records.length;
    }

    get isEditable() {
        return this.props.editable !== false;
    }

    async onCellClicked(record, column, ev) {
        if (!this.isEditable) {
            return;
        }

        return await super.onCellClicked(record, column, ev);
    }
}
CommonSkillsListRenderer.rowsTemplate = "hr_skills.SkillsListRenderer.Rows";
