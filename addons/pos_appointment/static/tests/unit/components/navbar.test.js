import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosAppointmentModels } from "../data/generate_model_definitions.js";

definePosAppointmentModels();

test("mainButton", async () => {
    const store = await setupPosEnv();
    store.router.state = {
        current: "ActionScreen",
        params: {
            actionName: "manage-booking",
        },
    };
    const navbar = await mountWithCleanup(Navbar, store.env);
    expect(navbar.mainButton).toBe("booking");
});
