import { describe, expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { definePosLoyaltyModels } from "@pos_loyalty/../tests/unit/data/generate_model_definitions";
import { addProductLineToOrder } from "@pos_loyalty/../tests/unit/utils";

definePosLoyaltyModels();

describe("pos.order.line - loyalty", () => {
    test("getEWalletGiftCardProgramType", async () => {
        const store = await setupPosEnv();
        const models = store.models;
        const order = store.addNewOrder();

        const program = models["loyalty.program"].get(2);

        const line = await addProductLineToOrder(store, order, {
            _e_wallet_program_id: program,
        });

        expect(line.getEWalletGiftCardProgramType()).toBe(`${program.program_type}`);
    });

    test("ignoreLoyaltyPoints", async () => {
        const store = await setupPosEnv();
        const models = store.models;
        const order = store.addNewOrder();

        const programA = models["loyalty.program"].get(2);
        const programB = models["loyalty.program"].get(4);

        const line = await addProductLineToOrder(store, order);
        line.update({ _e_wallet_program_id: programB });

        expect(line.ignoreLoyaltyPoints({ program: programA })).toBe(true);
    });

    test("getGiftCardOrEWalletBalance", async () => {
        const store = await setupPosEnv();
        const models = store.models;

        const card = models["loyalty.card"].get(3);

        const order = store.addNewOrder();

        const line = await addProductLineToOrder(store, order, {
            is_reward_line: true,
            coupon_id: card,
        });

        const balance = line.getGiftCardOrEWalletBalance();

        expect(balance).toBeOfType("string");
        expect(balance).toMatch(new RegExp(`${card.points}`));
    });
});
