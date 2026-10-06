// @ts-check

import { expect, test } from "@odoo/hoot";
import { drag, queryAllAttributes, queryAllTexts, queryOne } from "@odoo/hoot-dom";
import { advanceTime, animationFrame, Deferred } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    getService,
    makeMockEnv,
    mockService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { recentRecordsService } from "@web/core/recent_records_service";
import { _makeUser, user } from "@web/core/user";
import { HomeTiles } from "@web/webclient/home_menu/home_tiles/home_tiles";
import { HomeTilesModel } from "@web/webclient/home_menu/home_tiles/home_tiles_model";
import {
    MetricSettings,
    MetricTile,
} from "@web/webclient/home_menu/home_tiles/metric_tile";
import { RecentRecordsTile } from "@web/webclient/home_menu/home_tiles/recent_records_tile";

class ResUsersSettings extends webModels.ResUsersSettings {
    home_tiles = fields.Json();
    _records = [{ id: 1, home_tiles: null }];
}
defineModels([ResUsersSettings]);

const TYPES = {
    recent_records: { name: "Recently opened", sizes: ["1x1", "2x1"] },
    metric: { name: "Metric", sizes: ["1x1", "2x1"] },
};

/** @param {boolean} editing */
async function mountTiles(editing) {
    await makeMockEnv();
    const model = new HomeTilesModel({ orm: getService("orm") });
    return mountWithCleanup(HomeTiles, { props: { editing, model } });
}

/** @param {{ id: string, type: string, size: string }[]} tiles */
function withTiles(tiles) {
    patchWithCleanup(
        user,
        _makeUser({ user_settings: { id: 1, home_tiles: { version: 1, tiles } } }),
    );
}

test("configured tiles load in one call and show their records", async () => {
    withTiles([
        { id: "recent_records_1", type: "recent_records", size: "1x1" },
        { id: "gone_1", type: "gone", size: "1x1" },
    ]);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", ({ args }) => {
        expect.step(`get_tiles ${args[0].map((/** @type {any} */ r) => r.id)}`);
        return {
            recent_records_1: {
                data: {
                    records: [
                        {
                            res_model: "res.partner",
                            res_id: 7,
                            display_name: "Azure Interior",
                            model_name: "Contact",
                        },
                    ],
                },
            },
            gone_1: { error: "unavailable" },
        };
    });
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(`doAction ${action.res_model} ${action.res_id}`);
        },
    });
    await mountTiles(false);
    await animationFrame();

    expect.verifySteps(["get_tiles recent_records_1,gone_1"]);
    expect("[data-tile-type=recent_records] .o_home_tile_title").toHaveText(
        "Recently opened",
    );
    expect(".o_recent_record").toHaveText("Azure Interior\nContact");
    expect("[data-tile-type=gone] .o_home_data_tile_error").toHaveText(
        "This tile is no longer available to you.",
    );

    await contains(".o_recent_record").click();
    expect.verifySteps(["doAction res.partner 7"]);
});

test("a tile that fails to load says so while the others render", async () => {
    withTiles([{ id: "recent_records_1", type: "recent_records", size: "1x1" }]);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", () => ({ recent_records_1: { error: "failed" } }));
    await mountTiles(false);
    await animationFrame();

    expect(".o_home_data_tile_error").toHaveText("This tile could not be loaded.");
    expect(".o_home_data_tile").not.toHaveAttribute("aria-busy");
});

test("in customize mode a tile is added from the picker", async () => {
    withTiles([]);
    onRpc("get_tile_types", () => TYPES);
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(`update ${JSON.stringify(args[1])}`);
        return {
            id: 1,
            home_tiles: {
                version: 1,
                tiles: [
                    { id: "recent_records_1", type: "recent_records", size: "1x1" },
                ],
            },
        };
    });
    onRpc("get_tiles", () => ({ recent_records_1: { data: { records: [] } } }));
    await mountTiles(true);

    await contains(".o_home_data_tile_add_button").click();
    await contains(".o_home_data_tile_pick").click();
    await animationFrame();

    expect.verifySteps(['update [{"operation":"add","type":"recent_records"}]']);
    expect(".o_home_data_tile .o_home_data_tile_remove").toHaveCount(1);
    expect(".o_home_data_tile .o_home_tile_title").toHaveText("Recently opened");
    expect(".o_home_data_tile .o_home_tile_body").toHaveText(
        "Records you open appear here.",
    );
});

test("openings reach the server once per second, the latest last", async () => {
    onRpc("note_opened", ({ args }) => {
        expect.step(`note_opened ${JSON.stringify(args[0])}`);
        return null;
    });
    const env = await makeMockEnv();
    const recentRecords = recentRecordsService.start(env, { orm: getService("orm") });
    recentRecords.note("res.partner", 1);
    recentRecords.note("res.partner", 2);
    recentRecords.note("res.partner", 1);
    expect.verifySteps([]);

    await advanceTime(1000);
    expect.verifySteps([
        'note_opened [{"res_model":"res.partner","res_id":2},{"res_model":"res.partner","res_id":1}]',
    ]);
});

test("a metric shows its value and trend and opens what it counts", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(
                `doAction ${action.res_model} ${JSON.stringify(action.domain)}`,
            );
        },
    });
    await mountWithCleanup(MetricTile, {
        props: {
            data: {
                configured: true,
                name: "Late invoices",
                model: "res.partner",
                model_name: "Contact",
                domain: [["name", "ilike", "a"]],
                label: "Records",
                value: 1234,
                spark: [0, 1, 4, 2],
            },
            size: "1x1",
        },
    });
    expect(".o_metric_tile_value").toHaveText("1.2k");
    expect(".o_metric_tile small").toHaveText("Records · Late invoices");
    expect(".o_metric_tile_spark polyline").toHaveAttribute(
        "points",
        "0,24 33,18 67,0 100,12",
    );

    await contains(".o_metric_tile").click();
    expect.verifySteps(['doAction res.partner [["name","ilike","a"]]']);
});

test("an unconfigured metric points to customize mode", async () => {
    await mountWithCleanup(MetricTile, {
        props: { data: { configured: false }, size: "1x1" },
    });
    expect("p").toHaveText("Choose a favourite filter to follow in customize mode.");
});

test("an added metric opens its settings and saves the chosen favourite", async () => {
    withTiles([]);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_metric_choices", () => [
        {
            id: 3,
            name: "Customers",
            model_name: "Contact",
            measures: [
                { name: "__count", label: "Records" },
                { name: "credit", label: "Credit" },
            ],
        },
    ]);
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(`update ${JSON.stringify(args[1])}`);
        const tile = { id: "metric_1", type: "metric", size: "1x1" };
        if (args[1][0].operation === "configure") {
            Object.assign(tile, { settings: args[1][0].settings });
        }
        return { id: 1, home_tiles: { version: 1, tiles: [tile] } };
    });
    onRpc("get_tiles", ({ args }) => {
        expect.step(`get_tiles ${JSON.stringify(args[0][0].settings ?? null)}`);
        return { metric_1: { data: { configured: false } } };
    });
    await mountTiles(true);

    await contains(".o_home_data_tile_add_button").click();
    await contains(".o_home_data_tile_pick:contains(Metric)").click();
    await animationFrame();
    expect(".o_metric_settings_filter").toHaveValue("3");

    await contains(".o_metric_settings_measure").select("credit");
    await contains(".o_metric_settings_save").click();
    await animationFrame();
    expect(".o_metric_settings").toHaveCount(0);
    expect.verifySteps([
        'update [{"operation":"add","type":"metric"}]',
        "get_tiles null",
        'update [{"operation":"configure","id":"metric_1","settings":{"filter_id":3,"measure":"credit"}}]',
        'get_tiles {"filter_id":3,"measure":"credit"}',
    ]);
});

const THREE = [
    { id: "recent_records_1", type: "recent_records", size: "1x1" },
    { id: "metric_1", type: "metric", size: "1x1" },
    { id: "metric_2", type: "metric", size: "1x1" },
];

/** @param {string[]} order */
function movedTiles(order) {
    return order.map((id) => THREE.find((tile) => tile.id === id));
}

test("in customize mode a tile moves by its buttons and says where it went", async () => {
    withTiles(THREE);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", ({ args }) =>
        Object.fromEntries(
            args[0].map((/** @type {any} */ { id, type }) => [
                id,
                { data: type === "metric" ? { configured: false } : { records: [] } },
            ]),
        ),
    );
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(JSON.stringify(args[1]));
        return {
            id: 1,
            home_tiles: {
                version: 1,
                tiles: movedTiles(["metric_1", "recent_records_1", "metric_2"]),
            },
        };
    });
    await mountTiles(true);
    await animationFrame();
    expect(".o_home_data_tile:eq(0) .o_home_data_tile_move_earlier").toHaveAttribute(
        "disabled",
    );
    expect(".o_home_data_tile:eq(2) .o_home_data_tile_move_later").toHaveAttribute(
        "disabled",
    );

    await contains(".o_home_data_tile:eq(0) .o_home_data_tile_move_later").click();
    await animationFrame();
    expect.verifySteps(['[{"operation":"move","id":"recent_records_1","index":1}]']);
    expect(queryAllAttributes(".o_home_data_tile", "data-tile-id")).toEqual([
        "metric_1",
        "recent_records_1",
        "metric_2",
    ]);
    expect(".o_home_data_tiles [role=status]").toHaveText(
        "Recently opened moved to position 2",
    );
});

test("in customize mode a tile is dragged to its place", async () => {
    withTiles(THREE);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", () => ({}));
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(JSON.stringify(args[1]));
        return {
            id: 1,
            home_tiles: {
                version: 1,
                tiles: movedTiles(["metric_1", "metric_2", "recent_records_1"]),
            },
        };
    });
    await mountTiles(true);
    await animationFrame();

    const { moveTo, drop } = await drag(".o_home_data_tile:eq(0)");
    await moveTo(".o_home_data_tile:eq(0)", {
        position: { x: 10, y: 60 },
        relative: true,
    });
    await drop(".o_draggable:not(.o_dragged):eq(2)");
    await animationFrame();
    expect.verifySteps(['[{"operation":"move","id":"recent_records_1","index":2}]']);
    expect(queryAllAttributes(".o_home_data_tile", "data-tile-id")).toEqual([
        "metric_1",
        "metric_2",
        "recent_records_1",
    ]);
});

test("outside customize mode tiles do not move", async () => {
    withTiles(THREE);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", () => ({}));
    await mountTiles(false);
    await animationFrame();
    expect(".o_home_data_tile_move_later").toHaveCount(0);
    expect(".o_home_data_tile.o_draggable").toHaveCount(0);
});

test("a configure the server refuses leaves the tile showing what it had", async () => {
    withTiles([{ id: "recent_records_1", type: "recent_records", size: "1x1" }]);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", () => ({ recent_records_1: { data: { records: [] } } }));
    onRpc("update_home_tiles", () => {
        throw new Error("Invalid tile settings.");
    });
    const tiles = await mountTiles(true);
    await animationFrame();
    expect(".o_home_tile_body").toHaveText("Records you open appear here.");

    const [tile] = tiles.tiles;
    await expect(tiles.configure(tile, { limit: 3 })).rejects.toThrow();
    await animationFrame();
    expect(".o_home_data_tile").not.toHaveAttribute("aria-busy");
    expect(".o_home_tile_body").toHaveText("Records you open appear here.");
});

test("a tile's late answer does not overwrite the newer one", async () => {
    withTiles([{ id: "recent_records_1", type: "recent_records", size: "1x1" }]);
    onRpc("get_tile_types", () => TYPES);
    const answers = [new Deferred(), new Deferred()];
    let call = 0;
    onRpc("get_tiles", () => answers[call++]);
    onRpc("update_home_tiles", () => ({
        id: 1,
        home_tiles: {
            version: 1,
            tiles: [{ id: "recent_records_1", type: "recent_records", size: "2x1" }],
        },
    }));
    const tiles = await mountTiles(true);
    await animationFrame();
    await tiles.configure(tiles.tiles[0], { limit: 3 });
    await animationFrame();
    expect(call).toBe(2);

    const record = (/** @type {string} */ name) => ({
        recent_records_1: {
            data: {
                records: [
                    {
                        res_model: "res.partner",
                        res_id: 1,
                        display_name: name,
                        model_name: "Contact",
                    },
                ],
            },
        },
    });
    answers[1].resolve(record("Newer"));
    await animationFrame();
    answers[0].resolve(record("Older"));
    await animationFrame();
    expect(".o_recent_record").toHaveText("Newer\nContact");
});

test("a tile whose component fails says so while the others render", async () => {
    withTiles([
        { id: "recent_records_1", type: "recent_records", size: "1x1" },
        { id: "metric_1", type: "metric", size: "1x1" },
    ]);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", () => ({
        recent_records_1: { data: { unexpected: true } },
        metric_1: { data: { configured: false } },
    }));
    patchWithCleanup(console, {
        warn: (/** @type {string} */ message) => expect.step(message),
    });
    await mountTiles(false);
    await animationFrame();
    expect.verifySteps(["Home tile failed to render"]);
    expect("[data-tile-type=recent_records] .o_home_data_tile_error").toHaveText(
        "This tile could not be loaded.",
    );
    expect("[data-tile-type=metric] .o_home_tile_body").toHaveText(
        "Choose a favourite filter to follow in customize mode.",
    );
});

test("tile types that fail to load leave the tiles up and are asked again later", async () => {
    withTiles([{ id: "recent_records_1", type: "recent_records", size: "1x1" }]);
    let fail = true;
    onRpc("get_tile_types", () => {
        expect.step("get_tile_types");
        if (fail) {
            throw new Error("offline");
        }
        return TYPES;
    });
    onRpc("get_tiles", () => ({ recent_records_1: { data: { records: [] } } }));
    await mountTiles(true);
    await animationFrame();
    expect.verifySteps(["get_tile_types"]);
    expect(".o_home_tile_body").toHaveText("Records you open appear here.");

    fail = false;
    await contains(".o_home_data_tile_add_button").click();
    expect.verifySteps(["get_tile_types"]);
    expect(queryAllTexts(".o_home_data_tile_pick")).toEqual([
        "Recently opened",
        "Metric",
    ]);
});

test("a refused configure of a tile still loading loads it again", async () => {
    withTiles([{ id: "recent_records_1", type: "recent_records", size: "1x1" }]);
    onRpc("get_tile_types", () => TYPES);
    const first = new Deferred();
    let calls = 0;
    onRpc("get_tiles", () => {
        calls++;
        return calls === 1 ? first : { recent_records_1: { data: { records: [] } } };
    });
    onRpc("update_home_tiles", () => {
        throw new Error("Invalid tile settings.");
    });
    const tiles = await mountTiles(true);
    await animationFrame();
    await expect(tiles.configure(tiles.tiles[0], { limit: 3 })).rejects.toThrow();
    await animationFrame();
    expect(calls).toBe(2);
    expect(".o_home_tile_body").toHaveText("Records you open appear here.");
    first.resolve({
        recent_records_1: {
            data: {
                records: [
                    {
                        res_model: "res.partner",
                        res_id: 1,
                        display_name: "Stale",
                        model_name: "Contact",
                    },
                ],
            },
        },
    });
    await animationFrame();
    expect(".o_recent_record").toHaveCount(0);
});

test("tile changes reach the server one at a time, and saving holds until the last", async () => {
    withTiles([{ id: "recent_records_1", type: "recent_records", size: "1x1" }]);
    const answers = [new Deferred(), new Deferred()];
    let calls = 0;
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(args[1][0].operation);
        return answers[calls++];
    });
    await makeMockEnv();
    const model = new HomeTilesModel({ orm: getService("orm") });
    const layout = (/** @type {string} */ size) => ({
        id: 1,
        home_tiles: {
            version: 1,
            tiles: [{ id: "recent_records_1", type: "recent_records", size }],
        },
    });
    const resized = model.change([
        { operation: "resize", id: "recent_records_1", size: "2x1" },
    ]);
    const tinted = model.setBackground("teal");
    await animationFrame();
    expect.verifySteps(["resize"]);
    expect(model.state.saving).toBe(true);
    answers[0].resolve(layout("2x1"));
    await resized;
    await animationFrame();
    expect.verifySteps(["background"]);
    expect(model.state.saving).toBe(true);
    answers[1].resolve({
        ...layout("2x1"),
        home_tiles: { ...layout("2x1").home_tiles, background: "teal" },
    });
    await tinted;
    expect(model.state.saving).toBe(false);
    expect(model.state.background).toBe("teal");
});

test("a metric tile is titled by its favourite, and changes are announced", async () => {
    withTiles([
        { id: "metric_1", type: "metric", size: "1x1" },
        { id: "metric_2", type: "metric", size: "1x1" },
    ]);
    onRpc("get_tile_types", () => TYPES);
    onRpc("get_tiles", () => ({
        metric_1: {
            data: {
                configured: true,
                name: "Late invoices",
                label: "Records",
                value: 1,
                spark: [1],
            },
        },
        metric_2: { data: { configured: false } },
    }));
    onRpc("update_home_tiles", ({ args }) => ({
        id: 1,
        home_tiles: {
            version: 1,
            tiles:
                args[1][0].operation === "remove"
                    ? [{ id: "metric_2", type: "metric", size: "1x1" }]
                    : [
                          { id: "metric_1", type: "metric", size: "2x1" },
                          { id: "metric_2", type: "metric", size: "1x1" },
                      ],
        },
    }));
    await mountTiles(true);
    await animationFrame();
    expect(queryAllTexts(".o_home_data_tile .o_home_tile_title")).toEqual([
        "Late invoices",
        "Metric",
    ]);
    expect(".o_home_data_tile:eq(0) .o_home_data_tile_move_later").toHaveAttribute(
        "aria-label",
        "Move Late invoices later",
    );
    await contains(".o_home_data_tile:eq(0) .o_home_data_tile_resize").click();
    expect(".o_home_data_tiles > [role=status]").toHaveText(
        "Late invoices is now wide",
    );
    await contains(".o_home_data_tile:eq(0) .o_home_data_tile_remove").click();
    expect(".o_home_data_tiles > [role=status]").toHaveText("Late invoices removed");
});

test("a recently opened record links to its own address", async () => {
    await mountWithCleanup(RecentRecordsTile, {
        props: {
            data: {
                records: [
                    {
                        res_model: "res.partner",
                        res_id: 7,
                        display_name: "Azure",
                        model_name: "Contact",
                    },
                ],
            },
            size: "1x1",
        },
    });
    expect(".o_recent_record").toHaveAttribute("href", "/odoo/res.partner/7");
});

test("a metric whose favourite is gone offers the first one, and a failed list says so", async () => {
    const choices = [
        {
            id: 3,
            name: "Late",
            model_name: "Contact",
            measures: [{ name: "__count", label: "Count" }],
        },
    ];
    let fail = false;
    onRpc("get_metric_choices", () => {
        if (fail) {
            throw new Error("offline");
        }
        return choices;
    });
    const props = {
        settings: { filter_id: 99, measure: "amount" },
        onSave: (/** @type {any} */ settings) => expect.step(JSON.stringify(settings)),
        onCancel: () => {},
    };
    await mountWithCleanup(MetricSettings, { props });
    expect(".o_metric_settings_save").toBeEnabled();
    await contains(".o_metric_settings_save").click();
    expect.verifySteps(['{"filter_id":3,"measure":"__count"}']);

    fail = true;
    await mountWithCleanup(MetricSettings, { props });
    expect(".o_metric_settings_failed").toHaveText(
        "Your favourite filters could not be loaded.",
    );
    expect(".o_metric_settings_save:last").not.toBeEnabled();
});

test("a sparkline with negative weeks stays inside its box", async () => {
    await mountWithCleanup(MetricTile, {
        props: {
            data: {
                configured: true,
                name: "Balance",
                label: "Sum",
                value: 0,
                spark: [-2, 0, 2],
            },
            size: "1x1",
        },
    });
    expect(".o_metric_tile_spark polyline").toHaveAttribute(
        "points",
        "0,24 50,12 100,0",
    );
});

test("a record link opens the form on a click and leaves a modified click to the browser", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(`doAction ${action.res_model} ${action.res_id}`);
        },
    });
    await mountWithCleanup(RecentRecordsTile, {
        props: {
            data: {
                records: [
                    {
                        res_model: "res.partner",
                        res_id: 7,
                        display_name: "Azure",
                        model_name: "Contact",
                    },
                ],
            },
            size: "1x1",
        },
    });
    const link = queryOne(".o_recent_record");
    // bubbles right after the link's own handler, before HOOT's window-level
    // guard that keeps every anchor click from navigating the test page
    link.parentElement?.addEventListener("click", (ev) =>
        expect.step(`prevented ${ev.defaultPrevented}`),
    );
    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect.verifySteps(["doAction res.partner 7", "prevented true"]);
    link.dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true }),
    );
    expect.verifySteps(["prevented false"]);
});
