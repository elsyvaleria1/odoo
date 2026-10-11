import "./pos_order.data.js";
import "./pos_order_line.data.js";
import "./pos_session.data.js";
import "./product_product.data.js";

import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { LoyaltyCard } from "./loyalty_card.data.js";
import { LoyaltyProgram } from "./loyalty_program.data.js";
import { LoyaltyReward } from "./loyalty_reward.data.js";
import { LoyaltyRule } from "./loyalty_rule.data.js";

export const definePosLoyaltyModels = () => {
    definePosModels([LoyaltyCard, LoyaltyProgram, LoyaltyReward, LoyaltyRule]);
};
