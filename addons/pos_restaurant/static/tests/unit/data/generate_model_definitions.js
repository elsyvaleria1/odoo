import "./pos_order_line.data.js";
import "./pos_preset.data.js";
import "./pos_session.data.js";

import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { applyRestaurantConfigRecords } from "./pos_config.data.js";
import { RestaurantFloor } from "./restaurant_floor.data.js";
import { RestaurantOrderCourse } from "./restaurant_order_course.data.js";
import { RestaurantTable } from "./restaurant_table.data.js";

/** @param {Function[]} [extraModels=[]] */
export const definePosRestaurantModels = (extraModels = []) => {
    definePosModels([
        RestaurantFloor,
        RestaurantTable,
        RestaurantOrderCourse,
        ...extraModels,
    ]);
    beforeEach(applyRestaurantConfigRecords);
};
