import { expect, test } from "@odoo/hoot";

import { definePosModels } from "../data/generate_model_definitions.js";
import { expectFormattedPrice, setupPosEnv } from "../utils.js";
import { getFilledOrderForPriceCheck } from "./utils.js";

definePosModels();

test("Prices includes", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrderForPriceCheck(store);
    const details = order.prices.taxDetails;
    const line1 = order.lines[0].prices;
    const line2 = order.lines[1].prices;

    expect(details.base_amount).toBe(1100);
    expect(details.tax_amount).toBe(290);
    expect(details.total_amount).toBe(1390);

    expect(line1.total_included).toBe(1250);
    expect(line1.total_excluded).toBe(1000);
    expect(line1.taxes_data[0].tax_amount).toBe(250);
    expect(line1.taxes_data[0].tax.amount).toBe(25);

    expect(line2.total_included).toBe(140);
    expect(line2.total_excluded).toBe(100);
    expect(line2.taxes_data[0].tax_amount).toBe(15);
    expect(line2.taxes_data[0].tax.amount).toBe(15);
    expect(line2.taxes_data[1].tax_amount).toBe(25);
    expect(line2.taxes_data[1].tax.amount).toBe(25);

    expectFormattedPrice(order.currencyDisplayPrice, "$ 1,390.00");
    expectFormattedPrice(order.currencyAmountTaxes, "$ 290.00");
    expectFormattedPrice(order.lines[0].currencyDisplayPrice, "$ 1,250.00");
    expectFormattedPrice(order.lines[0].currencyDisplayPriceUnit, "$ 1,250.00");
    expectFormattedPrice(order.lines[0].currencyDisplayPriceUnitExcl, "$ 1,000.00");
    expectFormattedPrice(order.lines[1].currencyDisplayPrice, "$ 140.00");
    expectFormattedPrice(order.lines[1].currencyDisplayPriceUnit, "$ 140.00");
    expectFormattedPrice(order.lines[1].currencyDisplayPriceUnitExcl, "$ 100.00");
});

test("Prices excludes", async () => {
    const store = await setupPosEnv();
    store.config.iface_tax_included = "subtotal";
    const order = await getFilledOrderForPriceCheck(store);

    expectFormattedPrice(order.currencyDisplayPrice, "$ 1,100.00");
    expectFormattedPrice(order.lines[0].currencyDisplayPrice, "$ 1,000.00");
    expectFormattedPrice(order.lines[0].currencyDisplayPriceUnit, "$ 1,000.00");
    expectFormattedPrice(order.lines[1].currencyDisplayPrice, "$ 100.00");
    expectFormattedPrice(order.lines[1].currencyDisplayPriceUnit, "$ 100.00");
});

test("a combo parent's displayPrice carries the order sign on a refund", async () => {
    const store = await setupPosEnv();
    const models = store.models;
    const data = models.loadConnectedData({
        "pos.order": [
            { id: 2, name: "Combo order", is_refund: true, lines: [2, 3, 4] },
        ],
        "pos.order.line": [
            {
                id: 2,
                order_id: 2,
                product_id: 7,
                price_unit: 0.0,
                qty: -1,
                combo_line_ids: [3, 4],
                tax_ids: [],
            },
            {
                id: 3,
                order_id: 2,
                product_id: 8,
                price_unit: 1,
                qty: -2,
                combo_parent_id: 2,
                tax_ids: [],
            },
            {
                id: 4,
                order_id: 2,
                product_id: 10,
                price_unit: 8,
                qty: -1,
                combo_parent_id: 2,
                tax_ids: [],
            },
        ],
    });
    const [parent, child1, child2] = data["pos.order.line"];
    const order = data["pos.order"][0];

    expect(order.orderSign).toBe(-1);
    expect(child1.displayPrice).toBe(2);
    expect(child2.displayPrice).toBe(8);
    expect(parent.displayPrice).toBe(10);
    expect(parent.displayPrice).toBe(child1.displayPrice + child2.displayPrice);
});
