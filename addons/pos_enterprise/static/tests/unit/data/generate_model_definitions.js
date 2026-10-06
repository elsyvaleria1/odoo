import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { PosPrepLine } from "./pos_prep_line.data.js";
import { PosPrepOrder } from "./pos_prep_order.data.js";
import { PosPrepStage } from "./pos_prep_stage.data.js";
import { PosPrepState } from "./pos_prep_state.data.js";
import { PosPrepDisplay } from "./preparation_display.data.js";

export const definePosPrepDisplayModels = () => {
    definePosModels([
        PosPrepStage,
        PosPrepOrder,
        PosPrepLine,
        PosPrepState,
        PosPrepDisplay,
    ]);
};
