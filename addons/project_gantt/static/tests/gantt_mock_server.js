import { beforeEach } from "@odoo/hoot";
import { makeKwArgs, onRpc } from "@web/../tests/web_test_helpers";

function webGanttWrite({ args, kwargs, model }) {
    return this.env[model].write(...args, makeKwArgs({ context: kwargs.context }));
}

beforeEach(() => onRpc("web_gantt_write", webGanttWrite), { global: true });
