import { beforeEach } from "@odoo/hoot";
import { makeKwArgs, onRpc } from "@web/../tests/web_test_helpers";

function getGanttData({ kwargs, model }) {
    let groups = this.env[model].formatted_read_group({
        ...kwargs,
        aggregates: ["id:array_agg"],
        limit: null,
        offset: 0,
    });

    const length = groups.length;
    const offset = kwargs.offset || 0;
    groups = groups.slice(offset, kwargs.limit ? kwargs.limit + offset : undefined);

    const recordIds = [];
    for (const group of groups) {
        group.__record_ids = group["id:array_agg"];
        delete group["id:array_agg"];
        recordIds.push(...(group.__record_ids || []));
    }

    const { records } = this.env[model].web_search_read(
        [["id", "in", recordIds]],
        kwargs.read_specification,
        makeKwArgs({ context: kwargs.context }),
    );

    const unavailabilities = {};
    for (const fieldName of kwargs.unavailability_fields || []) {
        unavailabilities[fieldName] = {};
    }

    const progress_bars = {};
    for (const fieldName of kwargs.progress_bar_fields || []) {
        progress_bars[fieldName] = {};
    }

    return {
        groups,
        length,
        records,
        unavailabilities,
        progress_bars,
    };
}

// Register inside a global `beforeEach` (not module top-level) so the route is
// applied before every test under native ESM.
//
// CONSEQUENCE FOR CONSUMERS: a global `beforeEach` runs after any module-level
// `onRpc`, so this handler is registered LAST and wins. A downstream suite that
// wraps `get_gantt_data` at module level is never reached -- its `parent()` goes
// uncalled and the view gets this default instead, which for unavailabilities
// and progress bars is an empty object per requested field and so looks like
// data the server declined to send rather than a handler that did not run.
// Register such a wrapper from your own `beforeEach`; `parent()` then resolves
// to this one. `planning`'s contract-gantt suite lost four tests to it.
beforeEach(() => onRpc("get_gantt_data", getGanttData), { global: true });
