import { expect, test } from "@odoo/hoot";
import { tick } from "@odoo/hoot-dom";
import { CashMovePopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_popup";
import { patchTranslations, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { ConnectionLostError, RPCError } from "@web/core/network";

import { definePosModels } from "../data/generate_model_definitions.js";
import { mountPosDialog, setupPosEnv } from "../utils.js";

definePosModels();

const makeQueuedMove = async () => {
    const pos = await setupPosEnv();
    pos.data.network.unsyncData = [];
    pos.data.network.offline = false;
    const popup = await mountPosDialog(CashMovePopup, { close: () => {} });
    const notifications = [];
    patchWithCleanup(popup.notification, {
        add: (message, options) => {
            const notification = { message, options, closed: false };
            notifications.push(notification);
            return () => (notification.closed = true);
        },
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
    return { pos, notifications };
};

test("a cash move that has not reached the server is not reported as made", async () => {
    const { pos, notifications } = await makeQueuedMove();

    expect(pos.data.network.unsyncData).toHaveLength(1);
    expect(notifications).toHaveLength(1);
    expect(notifications[0].options.type).toBe("warning");
    expect(notifications[0].message).not.toInclude("Successfully");
    expect(notifications[0].message).toInclude("has not reached the server");
});

test("the queued cash move warning gives way to a success notice once the move is sent", async () => {
    const { pos, notifications } = await makeQueuedMove();
    patchWithCleanup(pos.data.orm, { call: async () => true });

    await pos.data.syncData();
    await tick();

    expect(notifications[0].closed).toBe(true);
    expect(notifications).toHaveLength(2);
    expect(String(notifications[1].message)).toMatch(
        /^Successfully made a cash in of \$\s9\.00\.$/,
    );
});

test("the queued cash move warning stays when the server refuses the move", async () => {
    const { pos, notifications } = await makeQueuedMove();
    patchWithCleanup(pos.data.dialog, { add: () => {} });
    patchWithCleanup(pos.data.orm, {
        call: async () => {
            throw new RPCError("Session closed");
        },
    });

    await pos.data.syncData();
    await tick();

    expect(pos.data.network.deadSyncData).toHaveLength(1);
    expect(notifications).toHaveLength(1);
    expect(notifications[0].closed).toBe(false);
});

test("the cash move journal line and receipt name the move with its own translated label", async () => {
    patchTranslations({
        point_of_sale: { in: "en", "Cash In": "Entrada de efectivo" },
    });
    const pos = await setupPosEnv();
    const popup = await mountPosDialog(CashMovePopup, { close: () => {} });
    const logged = [];
    const printed = [];
    patchWithCleanup(popup.printer, {
        print: async (_component, props) => printed.push(props),
    });
    patchWithCleanup(pos, {
        logEmployeeMessage: async (message) => logged.push(message),
    });
    patchWithCleanup(pos.data.orm, { call: async () => true });
    Object.assign(popup.state, { type: "in", amount: "9", reason: "float" });

    await popup.confirm();

    expect(logged).toHaveLength(1);
    expect(logged[0]).toMatch(/^Entrada de efectivo - /);
    expect(printed[0].label).toBe("Entrada de efectivo");
});
