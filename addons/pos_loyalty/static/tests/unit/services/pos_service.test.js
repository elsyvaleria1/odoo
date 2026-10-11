import { describe, expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { definePosLoyaltyModels } from "@pos_loyalty/../tests/unit/data/generate_model_definitions";
import { addProductLineToOrder } from "@pos_loyalty/../tests/unit/utils";
import { onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { toDate } from "@web/core/l10n/dates";

definePosLoyaltyModels();

describe("PosStore - loyalty essentials", () => {
    test("updatePrograms", async () => {
        const store = await setupPosEnv();
        const models = store.models;
        const order = store.addNewOrder();

        const partner = models["res.partner"].get(1);
        const program = models["loyalty.program"].get(5);

        models["loyalty.program"].getAll = () => [program];

        order.setPartner(partner);
        order._programIsApplicable = () => true;
        order._code_activated_coupon_ids = [];
        order.uiState.couponPointChanges = {};
        order.pricelist_id = { id: 1 };

        const line = await addProductLineToOrder(store, order, {
            gift_code: "XYZ123",
        });

        order.pointsForPrograms = () => ({
            [program.id]: [{ points: 10 }],
        });

        await store.updatePrograms();

        const changes = order.uiState.couponPointChanges;
        const changeList = Object.values(changes);

        expect(changeList).toHaveLength(1);
        expect(changeList[0].program_id).toBe(program.id);
        expect(changeList[0].points).toBe(10);
        expect(changeList[0].code).toBe("XYZ123");
        expect(changeList[0].product_id).toBe(line.product_id.id);
    });

    test("activateCode checks the program dates against the order date", async () => {
        onRpc("loyalty.card", "get_loyalty_card_partner_by_code", () => false);
        const store = await setupPosEnv();
        const order = store.addNewOrder();
        const program = store.models["loyalty.program"].get(6);
        const orderDay = toDate(order.date_order);

        expect(await store.activateCode("EXPIRED")).toBe(
            "That promo code program is expired.",
        );

        program.date_from = orderDay.add({ days: 1 });
        program.date_to = orderDay.add({ days: 10 });
        expect(await store.activateCode("EXPIRED")).toBe(
            "That promo code program is not yet valid.",
        );

        program.date_from = orderDay;
        program.date_to = orderDay;
        expect(await store.activateCode("EXPIRED")).toBe(true);
        expect(order.uiState.codeActivatedProgramRules).toInclude(3);
    });

    test("fetchLoyaltyCard", async () => {
        const store = await setupPosEnv();
        const models = store.models;

        const program = models["loyalty.program"].get(2);
        const partner = models["res.partner"].get(1);

        const card = await store.fetchLoyaltyCard(program.id, partner.id);

        expect(card.id).toBe(2);
    });
});

describe("PosStore - loyalty cards on the till", () => {
    test("a promotion card created on the till is written with the reward line using it, and restored with it", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = store.addNewOrder();
        const written = {};
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                (written[model] ??= []).push(...JSON.parse(JSON.stringify(rows)));
                return rows.map(() => ({ status: "fulfilled" }));
            },
        });
        data.listenToLocalChanges();

        const card = await store.couponForProgram(
            store.models["loyalty.program"].get(1),
        );
        const rewardLine = store.models["pos.order.line"].create({
            order_id: order,
            product_id: store.models["product.product"].get(1),
            qty: 1,
            price_unit: -1,
            is_reward_line: true,
            reward_id: store.models["loyalty.reward"].get(1),
            coupon_id: card,
        });
        data.debouncedSynchronizeLocalDataInIndexedDB.cancel();
        await data._synchronizeLocalDataInIndexedDB({ onlyDirty: true });

        expect(card.id).toBeLessThan(0);
        expect((written["loyalty.card"] ?? []).map((row) => row.id)).toEqual([card.id]);

        const rows = {
            "loyalty.card": written["loyalty.card"],
            "pos.order": written["pos.order"],
            "pos.order.line": written["pos.order.line"],
        };
        data.localDeleteCascade(order);
        card.delete();
        store.models.loadConnectedData(rows, []);

        const restored = store.models["pos.order.line"].getBy("uuid", rewardLine.uuid);
        expect(restored.coupon_id?.id).toBe(card.id);
    });
});
