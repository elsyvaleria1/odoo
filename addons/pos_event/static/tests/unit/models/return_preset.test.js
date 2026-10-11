import { describe, expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";

import { definePosEventModels } from "../data/generate_model_definitions.js";

definePosEventModels();

describe("switching an order to a return preset", () => {
    test("the event ticket line keeps the sign every other line just lost", async () => {
        const store = await setupPosEnv();
        const order = store.addNewOrder();
        const product = store.models["product.template"].get(5);

        const plainLine = store.models["pos.order.line"].create({
            order_id: order,
            product_id: product.product_variant_ids[0],
            qty: 2,
            price_unit: 10,
        });
        const ticketLine = store.models["pos.order.line"].create({
            order_id: order,
            product_id: product.product_variant_ids[0],
            qty: 1,
            price_unit: 10,
            event_ticket_id: store.models["event.event.ticket"].get(1),
        });

        const preset = store.models["pos.preset"].get(1);
        preset.is_return = true;
        order.setPreset(preset);

        expect(plainLine.qty).toBe(-2);
        expect(ticketLine.qty).toBe(1);
        expect(order.lines.some((l) => l.qty > 0)).toBe(true);
        expect(order.lines.some((l) => l.qty < 0)).toBe(true);
    });
});
