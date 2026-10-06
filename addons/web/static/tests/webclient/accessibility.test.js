// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineMenus,
    defineModels,
    fields,
    getAccessibilityViolations,
    getService,
    makeMockEnv,
    models,
    mountView,
    mountWebClient,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    preloadAxe,
    webModels,
} from "@web/../tests/web_test_helpers";
import { _makeUser, user } from "@web/core/user";
import { HomeTiles } from "@web/webclient/home_menu/home_tiles/home_tiles";
import { HomeTilesModel } from "@web/webclient/home_menu/home_tiles/home_tiles_model";
import { NavBar } from "@web/webclient/navbar/navbar";
import { WebClient } from "@web/webclient/webclient";

class Partner extends models.Model {
    name = fields.Char();
    email = fields.Char();
    active = fields.Boolean();
    birthday = fields.Date();
    parent_id = fields.Many2one({ relation: "partner" });
    state = fields.Selection({
        selection: [
            ["draft", "Draft"],
            ["done", "Done"],
        ],
    });

    _records = [
        {
            id: 1,
            name: "Azure",
            email: "azure@example.com",
            active: true,
            state: "draft",
        },
        { id: 2, name: "Deco", email: "deco@example.com", parent_id: 1, state: "done" },
    ];
}

class ResUsersSettings extends webModels.ResUsersSettings {
    home_tiles = fields.Json();
    _records = [{ id: 1, home_tiles: null }];
}

defineModels([Partner, ResUsersSettings]);

preloadAxe();

test.tags("desktop");
test("the home menu and its navbar have no accessibility violations", async () => {
    defineMenus([
        { id: 1, name: "Sales", appID: 1, actionID: 1001, xmlid: "app.sales" },
        { id: 2, name: "Inventory", appID: 2, actionID: 1002, xmlid: "app.inventory" },
    ]);
    await mountWebClient({ WebClient });
    await animationFrame();
    expect(await getAccessibilityViolations()).toEqual({});
});

test.tags("desktop");
test("the navbar inside an app has no accessibility violations", async () => {
    defineMenus([
        { id: 1, children: [2, 3], name: "Sales" },
        { id: 2, name: "Orders", actionID: 1001 },
        { id: 3, children: [4, 5], name: "Reporting" },
        { id: 4, name: "Sales Analysis", actionID: 1002 },
        { id: 5, name: "Pipeline", actionID: 1003 },
    ]);
    await makeMockEnv();
    getService("menu").setCurrentMenu(1);
    await mountWithCleanup(NavBar);
    expect(await getAccessibilityViolations()).toEqual({});

    await contains(".o_menu_sections .o-dropdown").click();
    expect(await getAccessibilityViolations()).toEqual({});
});

test("the home tiles in customize mode have no accessibility violations", async () => {
    patchWithCleanup(
        user,
        _makeUser({
            user_settings: {
                id: 1,
                home_tiles: {
                    version: 1,
                    tiles: [
                        { id: "recent_records_1", type: "recent_records", size: "2x1" },
                        { id: "metric_1", type: "metric", size: "1x1" },
                    ],
                },
            },
        }),
    );
    onRpc("get_tile_types", () => ({
        recent_records: { name: "Recently opened", sizes: ["1x1", "2x1"] },
        metric: { name: "Metric", sizes: ["1x1", "2x1"] },
    }));
    onRpc("get_tiles", () => ({
        recent_records_1: {
            data: {
                records: [
                    {
                        res_model: "partner",
                        res_id: 1,
                        display_name: "Azure",
                        model_name: "Contact",
                    },
                ],
            },
        },
        metric_1: { error: "unavailable" },
    }));
    await makeMockEnv();
    const model = new HomeTilesModel({ orm: getService("orm") });
    await mountWithCleanup(HomeTiles, { props: { editing: true, model } });
    await animationFrame();
    expect(await getAccessibilityViolations()).toEqual({});
});

test.tags("desktop");
test("a form view has no accessibility violations", async () => {
    await mountView({
        resModel: "partner",
        resId: 2,
        type: "form",
        arch: /* xml */ `
            <form>
                <header><field name="state" widget="statusbar"/></header>
                <sheet>
                    <group>
                        <group><field name="name"/><field name="email"/></group>
                        <group>
                            <field name="birthday"/>
                            <field name="parent_id"/>
                            <field name="active"/>
                        </group>
                    </group>
                </sheet>
            </form>`,
    });
    expect(await getAccessibilityViolations()).toEqual({});
});

test.tags("desktop");
test("a list view has no accessibility violations", async () => {
    await mountView({
        resModel: "partner",
        type: "list",
        arch: /* xml */ `
            <list>
                <field name="name"/>
                <field name="email"/>
                <field name="parent_id"/>
                <field name="active"/>
                <field name="state"/>
            </list>`,
    });
    expect(await getAccessibilityViolations()).toEqual({});

    await contains(".o_data_row:eq(0) .o_list_record_selector input").click();
    expect(await getAccessibilityViolations()).toEqual({});
});

test.tags("desktop");
test("the search bar's autocomplete has no accessibility violations", async () => {
    await mountView({
        resModel: "partner",
        type: "list",
        arch: /* xml */ `<list><field name="name"/></list>`,
        searchViewArch: /* xml */ `<search><field name="name"/><field name="email"/></search>`,
    });
    await contains(".o_searchview_input").edit("Az", { confirm: false });
    await animationFrame();
    expect(".o_searchview_autocomplete").toHaveCount(1);
    expect(await getAccessibilityViolations()).toEqual({});
});
