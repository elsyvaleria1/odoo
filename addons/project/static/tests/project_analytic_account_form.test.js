import { describe, expect, test } from "@odoo/hoot";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    toggleActionMenu,
    toggleMenuItem,
} from "@web/../tests/web_test_helpers";

import { defineProjectModels } from "./project_models.js";

class AccountAnalyticAccount extends models.Model {
    _name = "account.analytic.account";

    name = fields.Char();
    active = fields.Boolean({ default: true });
    project_count = fields.Integer();

    _records = [
        { id: 1, name: "Account A", project_count: 1 },
        { id: 2, name: "Account B", project_count: 1 },
    ];
}

defineProjectModels();
defineModels([AccountAnalyticAccount]);
describe.current.tags("desktop");

test("archiving lists the projects of the account on screen after paging", async () => {
    onRpc("project.project", "search_read", ({ kwargs }) => {
        const accountId = kwargs.domain[0][2];
        expect.step(`projects of ${accountId}`);
        return [{ id: accountId, name: `Project of account ${accountId}` }];
    });

    await mountView({
        resModel: "account.analytic.account",
        type: "form",
        arch: `
            <form js_class="analytic_account_form_view">
                <field name="name"/>
                <field name="active"/>
                <field name="project_count"/>
            </form>`,
        resId: 1,
        resIds: [1, 2],
        actionMenus: {},
    });
    await contains(".o_pager_next").click();
    expect(".o_field_widget[name=name] input").toHaveValue("Account B");

    await toggleActionMenu();
    await toggleMenuItem("Archive");

    expect.verifySteps(["projects of 2"]);
    expect(".modal-body").toHaveText(/Project of account 2/);
    expect(".modal-body").not.toHaveText(/Project of account 1/);
});
