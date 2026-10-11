/** @odoo-module native */
import { registry } from "@web/core/registry";

function _mockGetGanttData(params) {
    let groups = this.mockRpc({
        ...params,
        method: "formatted_read_group",
        aggregates: ["id:array_agg"],
    });
    if (params.limit) {
        groups = groups.slice(0, params.limit);
    }
    const length = groups.length;
    const ids = [];
    for (const g of groups) {
        g.__record_ids = g["id:array_agg"] || [];
        ids.push(...g.__record_ids);
    }
    const { records } = this.mockRpc({
        ...params,
        method: "web_search_read",
        recordIds: ids,
        specification: params.read_specification,
    });
    const fields = this.data[params.model].fields;
    const [startField, stopField] = Object.keys(params.read_specification).filter(
        (name) => ["date", "datetime"].includes(fields[name]?.type),
    );
    if (stopField) {
        for (const record of records) {
            if (
                record[startField] &&
                record[stopField] &&
                record[stopField] < record[startField]
            ) {
                [record[startField], record[stopField]] = [
                    record[stopField],
                    record[startField],
                ];
            }
        }
    }

    const unavailabilities = {};
    for (const fieldName of params.unavailability_fields || []) {
        unavailabilities[fieldName] = {};
    }

    const progress_bars = {};
    for (const fieldName of params.progress_bar_fields || []) {
        progress_bars[fieldName] = {};
    }

    return { groups, length, records, unavailabilities, progress_bars };
}

registry.category("sample_server").add("get_gantt_data", _mockGetGanttData);
