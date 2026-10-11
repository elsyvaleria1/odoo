import { expect, test } from "@odoo/hoot";
import { animationFrame, rightClick, runAllTimers, waitFor } from "@odoo/hoot-dom";
import { helpers, registries } from "@odoo/o-spreadsheet";
import { EventBus } from "@odoo/owl";
import {
    addGlobalFilter,
    setCellContent,
    setGlobalFilterValue,
} from "@spreadsheet/../tests/helpers/commands";
import { doMenuAction } from "@spreadsheet/../tests/helpers/ui";
import { insertPivot } from "@spreadsheet_edition/../tests/helpers/collaborative_helpers";
import {
    defineTestSpreadsheetEditionModels,
    SpreadsheetTest,
} from "@test_spreadsheet_edition/../tests/helpers/data";
import { createSpreadsheetTestAction } from "@test_spreadsheet_edition/../tests/helpers/helpers";
import {
    contains,
    getService,
    mockService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

const { cellMenuRegistry } = registries;
const { toZone } = helpers;

defineTestSpreadsheetEditionModels();

test("custom colors in color picker", async function () {
    onRpc("/spreadsheet/data/*", () => ({
        data: {},
        name: "test",
        company_colors: ["#875A7B", "not a valid color"],
    }));
    const { model } = await createSpreadsheetTestAction("spreadsheet_test_action");
    expect(model.getters.getCustomColors()).toEqual(["#875A7B"]);
});

test.tags("desktop");
test("preserve global filters when navigating through breadcrumb", async function () {
    const { model, env } = await createSpreadsheetTestAction("spreadsheet_test_action");
    await insertPivot(model);
    setCellContent(model, "A1", '=PIVOT.VALUE(1, "probability")');
    await addGlobalFilter(model, {
        id: "42",
        type: "relation",
        label: "Relation Filter",
        modelName: "product",
    });
    await setGlobalFilterValue(model, {
        id: "42",
        value: { operator: "in", ids: [37] },
    });
    await doMenuAction(cellMenuRegistry, ["pivot_see_records"], env);
    expect(".o_list_renderer").toHaveCount(1);
    await contains(".o_back_button").click();
    await contains(".o_topbar_filter_icon").click();
    expect(".o_multi_record_selector").toHaveText("xphone");
});

test("receives collaborative messages when action is restored", async function () {
    const mockBusService = {
        _bus: new EventBus(),
        subscribe(eventName, handler) {
            const listener = ({ detail }) => {
                if (detail.type === eventName) {
                    handler(detail.payload);
                }
            };
            const bus = this._bus;
            bus.addEventListener("notif", listener);
            return () => bus.removeEventListener("notif", listener);
        },
        notify(message) {
            this._bus.trigger("notif", message);
        },
    };
    mockService("bus_service", mockBusService);
    const spreadsheetData = {
        sheets: [
            {
                id: "sheet1",
                cells: {
                    A1: '=PIVOT.VALUE(1, "probability:sum")',
                },
            },
        ],
        pivots: {
            1: {
                type: "ODOO",
                columns: [],
                rows: [],
                domain: [],
                measures: [
                    {
                        id: "probability:sum",
                        fieldName: "probability",
                        aggregator: "sum",
                    },
                ],
                model: "partner",
            },
        },
    };
    const spreadsheetId = 1;
    SpreadsheetTest._records = [
        {
            id: spreadsheetId,
            name: "my test spreadsheet",
            spreadsheet_data: JSON.stringify(spreadsheetData),
        },
    ];
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "spreadsheet_test_action",
        params: {
            spreadsheet_id: 1,
            res_model: "spreadsheet.test",
        },
    });
    await animationFrame();
    await rightClick(".o-grid-overlay", { position: "top-left" });
    await animationFrame();
    await contains('.o-menu-item[data-name="pivot_see_records"]').click();
    await waitFor(".o_list_renderer");
    const revisionWebSocketMessage = {
        id: spreadsheetId,
        model: "spreadsheet.test",
        type: "REMOTE_REVISION",
        version: 1,
        serverRevisionId: "START_REVISION",
        nextRevisionId: "2",
        clientId: "raoul",
        commands: [
            {
                type: "SET_FORMATTING",
                sheetId: "sheet1",
                target: [toZone("A1")],
                style: { bold: true },
            },
        ],
    };
    // simulate a collaborative revision by pushing the revision
    // to the websocket bus.
    getService("bus_service").notify({
        id: spreadsheetId,
        type: "spreadsheet",
        payload: revisionWebSocketMessage,
    });
    await animationFrame();
    await contains(".o_back_button").click();
    expect('.o-menu-item-button[title="Bold (Ctrl+B)"]').toHaveClass("active");
});

test("the bus channel is released once nothing can bring the spreadsheet back", async function () {
    const spreadsheetStep = (step, name) => {
        if (name.startsWith("spreadsheet")) {
            expect.step(`${step} ${name}`);
        }
    };
    mockService("bus_service", {
        addChannel(channel) {
            spreadsheetStep("add", channel);
            const release = super.addChannel(channel);
            return () => {
                spreadsheetStep("delete", channel);
                release();
            };
        },
        subscribe(type, callback) {
            spreadsheetStep("subscribe", type);
            const unsubscribe = super.subscribe(type, callback);
            return () => {
                spreadsheetStep("unsubscribe", type);
                unsubscribe();
            };
        },
    });
    SpreadsheetTest._records = [
        { id: 1, name: "a spreadsheet", spreadsheet_data: "{}" },
    ];
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "spreadsheet_test_action",
        params: { spreadsheet_id: 1, res_model: "spreadsheet.test" },
    });
    await animationFrame();
    expect.verifySteps([
        "add spreadsheet_collaborative_session:spreadsheet.test:1",
        "subscribe spreadsheet",
    ]);

    await getService("action").doAction({
        type: "ir.actions.act_window",
        res_model: "partner",
        views: [[false, "list"]],
    });
    await contains(".o_back_button").click();
    expect.verifySteps([]);

    await getService("action").doAction(
        {
            type: "ir.actions.act_window",
            res_model: "partner",
            views: [[false, "list"]],
        },
        { clearBreadcrumbs: true },
    );
    expect.verifySteps([
        "unsubscribe spreadsheet",
        "delete spreadsheet_collaborative_session:spreadsheet.test:1",
    ]);
});

test("The geoJson service is given to the model for geo charts", async function () {
    const mockGeoJson = {
        type: "FeatureCollection",
        features: [
            {
                type: "Feature",
                id: "BE",
                properties: { name: "Belgium" },
                geometry: {},
            },
        ],
    };
    onRpc("/spreadsheet/static/topojson/world.topo.json", () => mockGeoJson);
    const { model } = await createSpreadsheetTestAction("spreadsheet_test_action", {});

    expect(model.getters.getGeoChartAvailableRegions().map((r) => r.label)).toEqual([
        "World",
        "Africa",
        "Asia",
        "Europe",
        "North America",
        "United States",
        "South America",
    ]);

    expect(model.getters.getGeoJsonFeatures("world")).toEqual(undefined);
    await runAllTimers();
    expect(model.getters.getGeoJsonFeatures("world")).toEqual([
        {
            type: "Feature",
            id: "BE",
            properties: { name: "Belgium" },
            geometry: {},
        },
    ]);
});
