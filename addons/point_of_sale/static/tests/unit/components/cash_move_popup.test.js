import { expect, test } from "@odoo/hoot";
import { CashMovePopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_popup";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { ConnectionLostError } from "@web/core/network";

import { definePosModels } from "../data/generate_model_definitions.js";
import { mountPosDialog, setupPosEnv } from "../utils.js";

definePosModels();

test("a cash move that has not reached the server is not reported as made", async () => {
    const pos = await setupPosEnv();
    pos.data.network.unsyncData = [];
    const popup = await mountPosDialog(CashMovePopup, { close: () => {} });
    const notifications = [];
    patchWithCleanup(popup.notification, {
        add: (message, options) => notifications.push({ message, options }),
    });
    patchWithCleanup(popup.printer, { print: async () => true });
    patchWithCleanup(pos, { logEmployeeMessage: async () => {} });
    patchWithCleanup(pos.data.orm, {
        call: async () => {
            throw new ConnectionLostError();
        },
    });
    Object.assign(popup.state, { type: "in", amount: "9", reason: "float" });

    await popup.confirm();

    expect(pos.data.network.unsyncData).toHaveLength(1);
    expect(notifications).toHaveLength(1);
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].message).not.toInclude("Successfully");
    expect(notifications[0].message).toInclude("has not reached the server");
});
