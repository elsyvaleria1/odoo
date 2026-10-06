import { expect, test } from "@odoo/hoot";
import { setupPosEnvForPrepDisplay } from "@pos_enterprise/../tests/unit/utils";
import { DeliveryButton } from "@pos_urban_piper/point_of_sale_overrirde/app/delivery_button/delivery_button";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosUrbanPiperModels } from "../data/generate_model_definitions.js";

definePosUrbanPiperModels();

test("handleToggle", async () => {
    const store = await setupPosEnvForPrepDisplay();
    const comp = await mountWithCleanup(DeliveryButton, {});
    store.saveProviderState({ doordash: false });
    expect(store.enabledProviders["doordash"]).toBe(true);
    comp.handleToggle("doordash");
    expect(store.enabledProviders["doordash"]).toBe(false);
});
