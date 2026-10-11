import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { definePosLoyaltyModels } from "@pos_loyalty/../tests/unit/data/generate_model_definitions";
import { addProductLineToOrder } from "@pos_loyalty/../tests/unit/utils";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";

definePosLoyaltyModels();

test("_applyReward", async () => {
    const store = await setupPosEnv();
    const models = store.models;
    const order = store.addNewOrder();

    const card = models["loyalty.card"].get(1);
    const reward = models["loyalty.reward"].get(2);

    await addProductLineToOrder(store, order);

    const potentialQty = order.getOrderlines().reduce((acc, line) => acc + line.qty, 0);

    const component = await mountWithCleanup(ControlButtons, {});

    const result = await component._applyReward(reward, card.id, potentialQty);

    expect(result).toBe(true);
});

test("getPotentialRewards", async () => {
    const store = await setupPosEnv();
    const models = store.models;
    const order = store.addNewOrder();

    const loyaltyProgram = models["loyalty.program"].get(1);
    const card = models["loyalty.card"].get(1);

    await addProductLineToOrder(store, order);
    order._code_activated_coupon_ids = [card];

    const component = await mountWithCleanup(ControlButtons, {});

    const rewards = component.getPotentialRewards();
    const reward = rewards[0].reward;

    expect(reward).toEqual(models["loyalty.reward"].get(1));
    expect(reward.program_id).toEqual(loyaltyProgram);
});
