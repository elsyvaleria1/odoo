import { beforeEach } from "@odoo/hoot";
import { makeKwArgs, onRpc } from "@web/../tests/web_test_helpers";

function webGanttWrite({ args, kwargs, model }) {
    return this.env[model].write(...args, makeKwArgs({ context: kwargs.context }));
}

// Register inside a global `beforeEach` (not module top-level) so the route is
// applied before every test under native ESM.
beforeEach(() => onRpc("web_gantt_write", webGanttWrite), { global: true });
