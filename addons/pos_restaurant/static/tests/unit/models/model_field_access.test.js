import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { definePosRestaurantModels } from "@pos_restaurant/../tests/unit/data/generate_model_definitions";
import { pick } from "@web/core/utils/collections/objects";

definePosRestaurantModels();

test("a table's fields survive pick(), which must not use Object.hasOwn", async () => {
    const store = await setupPosEnv();
    const table = store.models["restaurant.table"].getFirst();

    expect(Object.hasOwn(table, "position_h")).toBe(false);
    expect("position_h" in table).toBe(true);
    expect(typeof table.position_h).toBe("number");

    const geometry = pick(table, "position_h", "position_v", "width", "height");
    expect(Object.keys(geometry).sort()).toEqual([
        "height",
        "position_h",
        "position_v",
        "width",
    ]);
    expect(geometry.position_h).toBe(table.position_h);
    expect(geometry.position_v).toBe(table.position_v);

    expect(pick(table, "toString", "valueOf", "hasOwnProperty")).toEqual({});

    expect(Object.keys(pick(table, "constructor"))).toEqual(["constructor"]);
    expect(Object.hasOwn(Object.getPrototypeOf(table), "constructor")).toBe(true);
});
