import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { definePosRestaurantModels } from "@pos_restaurant/../tests/unit/data/generate_model_definitions";
import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";
import {
    getService,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { appContextOf } from "@web/core/app_context";
import { cookie } from "@web/core/browser/cookie";
import { ConnectionLostError } from "@web/core/network";

definePosRestaurantModels();

test("floor colors retain the POS scheme and translucent shade", async () => {
    await setupPosEnv();
    const screen = await mountWithCleanup(FloorScreen, {});
    let scheme = "light";
    const getCookie = cookie.get.bind(cookie);
    patchWithCleanup(cookie, {
        get: (name) => (name === "pos_color_scheme" ? scheme : getCookie(name)),
    });
    expect(screen.getColors().red).toBe("rgb(220,80,90)");
    expect(screen.getLighterShade("red")).toBe("rgb(220,80,90,0.75)");
    screen._getColors().red[0] = 0;
    expect(screen.getColors().red).toBe("rgb(220,80,90)");
    scheme = "dark";
    expect(screen.getColors().red).toBe("rgb(200,60,75)");
    expect(screen.getLighterShade("red")).toBe("rgb(200,60,75,0.75)");
});

test("getPosTable", async () => {
    const store = await setupPosEnv();
    store.currentFloor = store.models["restaurant.floor"].getFirst();
    const screen = await mountWithCleanup(FloorScreen, {});
    const renderedComp = await appContextOf(screen).services.renderer.toHtml(
        FloorScreen,
        {},
    );
    const table = screen.getPosTable(renderedComp.querySelector(".tableId-2"));
    expect(table.id).toBe(store.currentFloor.table_ids[0].id);
});

test.tags("desktop");
test("computeFloorSize", async () => {
    const store = await setupPosEnv();
    const floor = store.models["restaurant.floor"].get(2);
    store.currentFloor = floor;
    store.floorPlanStyle = "default";
    const screen = await mountWithCleanup(FloorScreen, {});
    Object.defineProperties(screen.floorScrollBox.el, {
        clientHeight: { value: 500 },
        offsetWidth: { value: 700 },
    });
    screen.state.floorMapOffset = { x: 0, y: 0 };
    screen.computeFloorSize();
    expect(screen.state.floorWidth).toBe("927px");
    expect(screen.state.floorHeight).toBe("500px");
});

test("resetTable", async () => {
    const store = await setupPosEnv();
    const table = store.models["restaurant.table"].get(1);
    const order = store.addNewOrder({ table_id: table });
    store.setOrder(order);
    const screen = await mountWithCleanup(FloorScreen, {});
    await screen.resetTable();
    expect(store.getOrder()).toBe(undefined);
});

test("pinch gesture computes scale and sets it", async () => {
    await setupPosEnv();
    const screen = await mountWithCleanup(FloorScreen, {});
    screen.getScale = () => 1;
    let scaleValue = null;
    screen.setScale = (value) => {
        scaleValue = value;
    };
    const startEvent = {
        touches: [
            { pageX: 0, pageY: 0 },
            { pageX: 0, pageY: 100 },
        ],
        currentTarget: {
            style: {
                setProperty: () => {},
            },
        },
    };
    screen._onPinchStart(startEvent);
    const hypotStart = Math.hypot(0 - 0, 0 - 100);
    expect(screen.scalehypot).toBe(hypotStart);
    expect(screen.initalScale).toBe(1);
    const moveEvent = {
        touches: [
            { pageX: 0, pageY: 0 },
            { pageX: 0, pageY: 200 },
        ],
    };
    screen._computePinchHypo(moveEvent, screen.movePinch.bind(screen));
    expect(scaleValue).toBeCloseTo(2);
});

test.tags("desktop");
test("_createTableHelper", async () => {
    const store = await setupPosEnv();
    const floor = store.models["restaurant.floor"].get(2);
    const screen = await mountWithCleanup(FloorScreen, {});
    screen.selectFloor(floor);
    const table = await screen._createTableHelper(null);
    expect(Boolean(table)).toBe(true);
    expect(table.floor_id.id).toBe(floor.id);
    expect(table.table_number).toBe(5);
    expect(table.height).toBe(table.width);
    expect(table.position_v >= 0).toBe(true);
    expect(table.position_h >= 10).toBe(true);
});

test.tags("desktop");
test("a table created offline is queued and nothing is selected", async () => {
    const store = await setupPosEnv();
    const floor = store.models["restaurant.floor"].get(2);
    const screen = await mountWithCleanup(FloorScreen, {});
    screen.selectFloor(floor);
    store.data.network.unsyncData = [];
    patchWithCleanup(store.data.orm, {
        create: async () => {
            throw new ConnectionLostError();
        },
    });
    const tables = store.models["restaurant.table"].length;

    await screen.createTable();

    expect(screen.state.selectedTableIds).toEqual([]);
    expect(store.models["restaurant.table"].length).toBe(tables);
    expect(store.data.network.unsyncData.map(({ args: [op] }) => op.model)).toEqual([
        "restaurant.table",
    ]);
});

test.tags("desktop");
test("a second table click while one waits for the connection queues nothing more", async () => {
    const store = await setupPosEnv();
    const notified = [];
    patchWithCleanup(getService("notification"), {
        add: (message, options) => notified.push([String(message), options?.type]),
    });
    const floor = store.models["restaurant.floor"].get(2);
    const screen = await mountWithCleanup(FloorScreen, {});
    screen.selectFloor(floor);
    store.data.network.unsyncData = [];
    patchWithCleanup(store.data.orm, {
        create: async () => {
            throw new ConnectionLostError();
        },
    });

    await screen.createTable();
    await screen.createTable();
    screen.state.selectedTableIds = [floor.table_ids[0].id];
    await screen.duplicateTable();

    expect(store.data.network.unsyncData).toHaveLength(1);
    expect(notified).toEqual([
        [
            "You are offline. The table will be created once the connection is back.",
            "warning",
        ],
        ["A new table is already waiting for the connection to come back.", "warning"],
        ["A new table is already waiting for the connection to come back.", "warning"],
    ]);
});

test("_getNewTableNumber", async () => {
    const store = await setupPosEnv();
    const floor = store.models["restaurant.floor"].getFirst();
    const screen = await mountWithCleanup(FloorScreen, {});
    screen.selectFloor(floor);
    const newNumber = screen._getNewTableNumber();
    expect(newNumber).toBe(5);
});

test("duplicateTable", async () => {
    const store = await setupPosEnv();
    const floor = store.models["restaurant.floor"].getFirst();
    const screen = await mountWithCleanup(FloorScreen, {});
    screen.selectFloor(floor);
    screen.state.selectedTableIds = [floor.table_ids[0].id];
    await screen.duplicateTable();
    expect(screen.state.selectedTableIds.length).toBe(1);
    const newTableId = screen.state.selectedTableIds[0];
    expect(newTableId).not.toBe(floor.table_ids[0].id);
});

test("_isTableVisible", async () => {
    const store = await setupPosEnv();
    const floor = store.models["restaurant.floor"].getFirst();
    const screen = await mountWithCleanup(FloorScreen, {});
    screen.selectFloor(floor);
    Object.defineProperties(screen.floorScrollBox.el, {
        clientHeight: { value: 500 },
        clientWidth: { value: 500 },
    });
    const table = store.models["restaurant.table"].get(2);
    expect(screen._isTableVisible(table)).toBe(true);
});
