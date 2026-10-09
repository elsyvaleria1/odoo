import { expect, test } from "@odoo/hoot";

import { definePosModels } from "../data/generate_model_definitions.js";
import { setupPosEnv } from "../utils.js";

definePosModels();

test("toMinorUnits rounds to the currency's minor unit instead of truncating", async () => {
    const store = await setupPosEnv();
    const usd = store.models["res.currency"].get(1);
    const yen = store.models["res.currency"].create({
        id: 9999,
        name: "JPY",
        rounding: 1,
        decimal_places: 0,
    });

    expect(
        [19.99, 1.15, 0.29, 4.35, 100.1, 1.005, -19.99].map((amount) =>
            usd.toMinorUnits(amount),
        ),
    ).toEqual([1999, 115, 29, 435, 10010, 101, -1999]);
    expect(yen.toMinorUnits(1500.4)).toBe(1500);
});
