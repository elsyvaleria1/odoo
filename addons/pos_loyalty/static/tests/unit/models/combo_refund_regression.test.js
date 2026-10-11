import { describe, expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { definePosLoyaltyModels } from "@pos_loyalty/../tests/unit/data/generate_model_definitions";

definePosLoyaltyModels();

const addLine = async (store, order, tmplId, qty, vals = {}, opts = {}) =>
    await store.addLineToOrder(
        {
            product_tmpl_id: store.models["product.template"].get(tmplId),
            qty,
            ...vals,
        },
        order,
        { force: true, ...opts },
        false,
    );

const setupComboOrder = async (
    store,
    { qty = 2, isRefund = false, withPlain = true } = {},
) => {
    const order = store.addNewOrder();
    order.is_refund = isRefund;
    const sign = isRefund ? -1 : 1;

    const parent = await addLine(store, order, 5, sign, { price_unit: 0 });
    const child1 = await addLine(store, order, 6, sign * qty);
    const child2 = await addLine(store, order, 8, sign * qty);
    child1.combo_parent_id = parent;
    child2.combo_parent_id = parent;
    const plain = withPlain ? await addLine(store, order, 9, sign * qty) : null;

    return { order, parent, children: [child1, child2], plain };
};

describe("combo totals — the pos_loyalty-facing pair", () => {
    test("comboTotalPriceWithoutTax counts quantity, not a unit price", async () => {
        const store = await setupPosEnv();
        const { parent, children } = await setupComboOrder(store, { qty: 3 });

        const lineTotals = children.reduce((s, l) => s + l.prices.total_excluded, 0);
        const unitTotals = children.reduce(
            (s, l) => s + l.unitPrices.total_excluded,
            0,
        );

        expect(parent.comboTotalPriceWithoutTax).toBe(lineTotals);
        expect(unitTotals).not.toBe(lineTotals);
        expect(children.every((l) => l.prices.total_excluded !== 0)).toBe(true);
    });

    test("the pair is independent of the iface_tax_included display setting", async () => {
        const store = await setupPosEnv();
        const { order, parent } = await setupComboOrder(store);
        const config = order.config;

        config.iface_tax_included = "total";
        const withTax = parent.comboTotalPrice;
        const withoutTax = parent.comboTotalPriceWithoutTax;
        expect(withTax).not.toBe(withoutTax);

        config.iface_tax_included = "subtotal";
        expect(parent.comboTotalPrice).toBe(withTax);
        expect(parent.comboTotalPriceWithoutTax).toBe(withoutTax);
    });

    test("a refund's combo totals are quantity-aware and carry the refund's sign", async () => {
        const store = await setupPosEnv();
        const { order, parent, children } = await setupComboOrder(store, {
            qty: 2,
            isRefund: true,
        });
        order.config.iface_tax_included = "total";

        expect(parent.comboTotalPriceWithoutTax).toBeLessThan(0);
        expect(parent.comboTotalPrice).toBeLessThan(0);
        expect(parent.comboTotalPriceWithoutTax).toBe(
            children.reduce((s, l) => s + l.prices.total_excluded, 0),
        );
        expect(parent.displayPrice).toBe(-parent.comboTotalPrice);
    });
});

describe("combo totals on refunds — sign convention", () => {
    test("a refund's combo branch agrees in sign with its plain-line branch", async () => {
        const store = await setupPosEnv();
        const { parent, plain } = await setupComboOrder(store, {
            qty: 2,
            isRefund: true,
        });

        expect(parent.comboTotalPriceWithoutTax).not.toBe(0);
        expect(plain.prices.total_excluded).not.toBe(0);
        expect(Math.sign(parent.comboTotalPriceWithoutTax)).toBe(
            Math.sign(plain.prices.total_excluded),
        );
        expect(Math.sign(parent.comboTotalPrice)).toBe(
            Math.sign(plain.prices.total_included),
        );
        expect(plain.comboTotalPrice).toBe(plain.prices.total_included);
    });

    test("refunding a combo onto a gift card earns no points, like refunding a plain line", async () => {
        const store = await setupPosEnv();
        const models = store.models;
        const program = models["loyalty.program"].get(1);
        const giftCardProgram = models["loyalty.program"].get(3);
        program.rule_ids[0].update({
            any_product: true,
            reward_point_mode: "money",
            reward_point_amount: 1,
            reward_point_split: false,
            minimum_qty: 0,
            minimum_amount: 10,
            minimum_amount_tax_mode: "incl",
        });

        const creditToGiftCard = async (order) =>
            await addLine(
                store,
                order,
                10,
                1,
                { price_unit: -order.priceIncl, tax_ids: [] },
                { eWalletGiftCardProgram: giftCardProgram },
            );

        const { order: comboRefund } = await setupComboOrder(store, {
            qty: 1,
            isRefund: true,
            withPlain: false,
        });
        await creditToGiftCard(comboRefund);

        const plainRefund = store.addNewOrder();
        plainRefund.is_refund = true;
        await addLine(store, plainRefund, 9, -1);
        await creditToGiftCard(plainRefund);

        expect(comboRefund.priceIncl).toBe(0);
        expect(plainRefund.priceIncl).toBe(0);
        expect(plainRefund.pointsForPrograms([program])[program.id]).toEqual([]);
        expect(comboRefund.pointsForPrograms([program])[program.id]).toEqual([]);
    });
});
