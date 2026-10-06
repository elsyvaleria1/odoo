// @ts-check

import { expect, test } from "@odoo/hoot";
import { Component, useProps, xml } from "@odoo/owl";
import {
    contains,
    defineModels,
    fields,
    mockService,
    models,
    mountView,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";

class Partner extends models.Model {
    name = fields.Char();
    _records = [{ id: 1, name: "first" }];
}

const { ResCompany, ResPartner, ResUsers } = webModels;

defineModels([Partner, ResCompany, ResPartner, ResUsers]);

const ARCH = `<form><field name="name"/></form>`;
const CONFIG = { actionId: 1, actionType: "ir.actions.act_window" };

class OtherCogItem extends Component {
    static props = null;
    static template = xml`<span class="o_other_cog_item">Other</span>`;
    props = useProps(this.constructor.props);
}

function addOtherCogItem() {
    registry
        .category("cogMenu")
        .add(
            "test-other",
            { Component: OtherCogItem, groupNumber: COG_GROUP.APP },
            { force: true },
        );
}

test("a saved record's cog menu asks why the user can see it", async () => {
    mockService("action", {
        async doAction(action, options) {
            expect.step([action, options?.additionalContext]);
        },
    });
    await mountView({
        resModel: "partner",
        type: "form",
        resId: 1,
        arch: ARCH,
        config: CONFIG,
    });
    await contains(".o_cp_action_menus button").click();
    expect(".o_explain_access").toHaveText("Why can I see this?");
    await contains(".o_explain_access").click();
    expect.verifySteps([
        ["base.action_ir_access_explain", { explain_model: "partner", explain_id: 1 }],
    ]);
});

test("a record not yet saved has nothing to explain", async () => {
    addOtherCogItem();
    await mountView({ resModel: "partner", type: "form", arch: ARCH, config: CONFIG });
    await contains(".o_cp_action_menus button").click();
    expect(".o_other_cog_item").toHaveCount(1);
    expect(".o_explain_access").toHaveCount(0);
});

test("a user outside the internal users is not offered it", async () => {
    addOtherCogItem();
    patchWithCleanup(user, { isInternalUser: false });
    await mountView({
        resModel: "partner",
        type: "form",
        resId: 1,
        arch: ARCH,
        config: CONFIG,
    });
    await contains(".o_cp_action_menus button").click();
    expect(".o_other_cog_item").toHaveCount(1);
    expect(".o_explain_access").toHaveCount(0);
});

test("only an action's form record is explained", async () => {
    const { isDisplayed } = registry.category("cogMenu").get("explain-access");
    const model = { root: { resId: 1 } };
    // isDisplayed reads only the view's config and model: a stub stands for the env
    const env = (/** @type {object} */ config) =>
        /** @type {import("@web/env").OdooEnv} */ (
            /** @type {unknown} */ ({ config, model })
        );
    const config = (/** @type {string} */ viewType) => ({ ...CONFIG, viewType });
    expect(isDisplayed(env(config("form")))).toBe(true);
    expect(isDisplayed(env(config("list")))).toBe(false);
    expect(isDisplayed(env(config("kanban")))).toBe(false);
    expect(isDisplayed(env({ viewType: "form" }))).toBe(false);
});
