import { expect, test } from "@odoo/hoot";
import { PosOrderAccounting } from "@point_of_sale/app/models/accounting/pos_order_accounting";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosModels } from "../data/generate_model_definitions.js";
import { getFilledOrder, setupPosEnv } from "../utils.js";

definePosModels();

function countComputes() {
    const counter = { n: 0 };
    patchWithCleanup(PosOrderAccounting.prototype, {
        _computeAllPrices() {
            counter.n++;
            return super._computeAllPrices(...arguments);
        },
    });
    return counter;
}

test("no-discount order: one recompute, no redundant no-discount pass", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const before = order.prices.taxDetails.total_amount;
    const counter = countComputes();

    counter.n = 0;
    order.lines[0].qty = 10;
    const details = order.prices.taxDetails;
    void order.unitPrices;
    void order.lines[0].prices;

    expect(counter.n).toBe(2);

    expect(order.lines[0].qty).toBe(10);
    expect(details.total_amount).toBeGreaterThan(before);

    const line = order.lines[0].prices;
    expect(line.discount_amount).toBe(0);
    expect(line.no_discount_total_included).toBe(line.total_included);
    expect(line.no_discount_total_excluded).toBe(line.total_excluded);
});

test("discounted order still runs the no-discount pass and reports the discount", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const counter = countComputes();

    counter.n = 0;
    order.lines[0].discount = 20;
    void order.prices;
    void order.unitPrices;

    expect(counter.n).toBe(4);

    const line = order.lines[0].prices;
    expect(line.discount_amount).toBeGreaterThan(0);
    expect(line.no_discount_total_included).toBeGreaterThan(line.total_included);
});

test("combo parent setQuantity coalesces child updates into one recompute", async () => {
    const store = await setupPosEnv();
    store.models["product.combo"].get(1).qty_free = 2;
    const comboProduct1 = store.models["product.combo.item"].get(1);
    const comboProduct2 = store.models["product.combo.item"].get(3);
    const template = store.models["product.template"].get(7);
    const order = store.addNewOrder();
    await store.addLineToOrder(
        {
            product_tmpl_id: template,
            payload: [
                [{ combo_item_id: comboProduct1, qty: 2 }],
                [{ combo_item_id: comboProduct2, qty: 2 }],
            ],
            qty: 1,
        },
        order,
    );
    const parent = order.lines.find((l) => l.combo_line_ids.length);
    const counter = countComputes();

    counter.n = 0;
    parent.setQuantity(3);
    const total = order.prices.taxDetails.total_amount;
    void order.unitPrices;

    expect(counter.n).toBe(2);
    expect(parent.qty).toBe(3);
    expect(total).toBeGreaterThan(0);
});

function loadOrder(store, lineCount, { id = 6000, discounted = true } = {}) {
    const lineIds = Array.from({ length: lineCount }, (_, i) => id * 1000 + i);
    return store.models.loadConnectedData({
        "pos.order": [{ id, name: `Order ${id}`, lines: lineIds }],
        "pos.order.line": lineIds.map((lineId, i) => ({
            id: lineId,
            order_id: id,
            product_id: 5,
            qty: 1,
            price_unit: 10 + i,
            tax_ids: [1],
            discount: discounted && i % 2 ? 5 : 0,
        })),
    })["pos.order"][0];
}

test("setOrderPrices runs one price computation whatever the line count", async () => {
    const store = await setupPosEnv();
    const counter = countComputes();
    for (const [lineCount, id] of [
        [10, 6010],
        [40, 6040],
    ]) {
        const order = loadOrder(store, lineCount, { id });
        counter.n = 0;
        order.setOrderPrices();
        expect(counter.n).toBe(2);

        counter.n = 0;
        void order.prices;
        expect(counter.n).toBe(0);
    }
});

test("writing a line field the taxes do not read keeps the order prices", async () => {
    const store = await setupPosEnv();
    const order = loadOrder(store, 5);
    const line = order.lines[0];
    void order.prices;
    const counter = countComputes();

    line.customer_note = "no onions";
    line.price_subtotal = 1;
    void order.prices;
    expect(counter.n).toBe(0);

    line.qty = 2;
    void order.prices;
    expect(counter.n).toBe(2);
});
