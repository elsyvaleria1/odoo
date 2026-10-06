/** @odoo-module native */
import { GanttArchParser } from "@web_gantt/gantt_arch_parser";

export class TaskGanttArchParserCommon extends GanttArchParser {
    parse() {
        const archInfo = super.parse(...arguments);
        const decorationFields = new Set([...archInfo.decorationFields, "project_id"]);
        if (archInfo.dependencyEnabled) {
            decorationFields.add("allow_dependencies");
        }
        return {
            ...archInfo,
            decorationFields: [...decorationFields],
        };
    }
}
