import { defineHrPayrollModels } from "@hr_payroll/../tests/hr_payroll_test_helpers";
import { PayrollDashboardTodo } from "@hr_payroll/components/dashboard/todo_list/todo_list";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { queryOne, unload, waitFor } from "@odoo/hoot-dom";
import { tick } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    models,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineHrPayrollModels();

class HrPayrollNote extends models.Model {
    _name = "hr.payroll.note";

    name = fields.Char();
    note = fields.Html();
    company_id = fields.Many2one({ relation: "res.company" });

    _records = [{ id: 1, name: "Checklist", note: "<p>abc</p>" }];
}

defineModels([HrPayrollNote]);

beforeEach(() => {
    onRpc("/html_editor/get_ice_servers", () => []);
    onRpc("/html_editor/bus_broadcast", () => ({ id: 10 }));
});

async function closeTheTab() {
    const [ev] = await unload();
    await tick();
    return ev.defaultPrevented;
}

test("closing the tab with an unsaved note asks to stay", async () => {
    await mountWithCleanup(PayrollDashboardTodo, { props: { orderBy: [] } });
    await waitFor(".odoo-editor-editable p");
    queryOne(".odoo-editor-editable p").append(document.createTextNode("d"));
    expect(await closeTheTab()).toBe(true);
});

test("closing the tab with an untouched note does not ask", async () => {
    await mountWithCleanup(PayrollDashboardTodo, { props: { orderBy: [] } });
    await waitFor(".odoo-editor-editable p");
    expect(await closeTheTab()).toBe(false);
});
