// @ts-check

import { expect, test } from "@odoo/hoot";
import { advanceTime, animationFrame, Deferred } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    toggleMenuItem,
    toggleSearchBarMenu,
} from "@web/../tests/web_test_helpers";

class Note extends models.Model {
    name = fields.Char();

    _records = [
        { id: 1, name: "first" },
        { id: 2, name: "second" },
    ];
}

defineModels([Note]);

const searchViewArch = `
    <search>
        <filter name="first" string="First" domain="[('id', '=', 1)]"/>
    </search>
`;

/** @param {() => Promise<unknown> | null} gate */
function holdSearchRead(gate) {
    onRpc("web_search_read", async () => {
        await gate();
    });
}

test("a slow reload keeps its results on screen and marks them stale after the loading threshold", async () => {
    let pending = /** @type {any} */ (null);
    holdSearchRead(() => pending);
    await mountView({
        resModel: "note",
        type: "list",
        arch: `<list><field name="name"/></list>`,
        searchViewArch,
    });
    expect(".o_content").not.toHaveAttribute("aria-busy");

    pending = new Deferred();
    await toggleSearchBarMenu();
    await toggleMenuItem("First");
    await advanceTime(200);
    expect(".o_content").toHaveAttribute("aria-busy", "true");
    expect(".o_content").not.toHaveClass("o_view_stale");

    await advanceTime(60);
    expect(".o_content").toHaveClass("o_view_stale");
    expect(".o_data_row").toHaveCount(2, {
        message: "the results being replaced are still the ones on screen",
    });
    expect(".o_skeleton_view").toHaveCount(0);

    pending.resolve();
    await animationFrame();
    await animationFrame();
    expect(".o_content").not.toHaveClass("o_view_stale");
    expect(".o_content").not.toHaveAttribute("aria-busy");
    expect(".o_data_row").toHaveCount(1);
});

test("a quick reload is never marked stale", async () => {
    await mountView({
        resModel: "note",
        type: "list",
        arch: `<list><field name="name"/></list>`,
        searchViewArch,
    });
    await toggleSearchBarMenu();
    await toggleMenuItem("First");
    await advanceTime(300);

    expect(".o_content").not.toHaveClass("o_view_stale");
    expect(".o_skeleton_view").toHaveCount(0);
    expect(".o_data_row").toHaveCount(1);
});

test("switching to a slow record keeps the current one on screen, stale", async () => {
    let pending = /** @type {any} */ (null);
    onRpc("web_read", async () => {
        await pending;
    });
    await mountView({
        resModel: "note",
        type: "form",
        arch: `<form><field name="name"/></form>`,
        resId: 1,
        resIds: [1, 2],
    });

    pending = new Deferred();
    await contains(".o_pager_next").click();
    await advanceTime(260);
    expect(".o_content").toHaveClass("o_view_stale");
    expect(".o_skeleton_view").toHaveCount(0);
    expect(".o_field_widget[name=name] input").toHaveValue("first");

    pending.resolve();
    await animationFrame();
    await animationFrame();
    expect(".o_content").not.toHaveClass("o_view_stale");
    expect(".o_field_widget[name=name] input").toHaveValue("second");
});

test("a view that paints before its first data shows its skeleton until the data lands", async () => {
    const pending = new Deferred();
    holdSearchRead(() => pending);
    await mountView({
        resModel: "note",
        type: "list",
        arch: `<list><field name="name"/></list>`,
        searchViewArch,
    });

    expect(".o_control_panel").toHaveCount(1);
    expect(".o_content").toHaveClass("o_view_loading");
    expect(".o_content").toHaveAttribute("aria-busy", "true");
    expect(".o_content.o_view_loading > .o_view_busy .o_skeleton_list").toHaveCount(1);

    pending.resolve();
    await animationFrame();
    await animationFrame();
    expect(".o_content").not.toHaveClass("o_view_loading");
    expect(".o_content").not.toHaveAttribute("aria-busy");
    expect(".o_skeleton_view").toHaveCount(0);
    expect(".o_data_row").toHaveCount(2);
});
