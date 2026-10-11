import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import {
    contains,
    mockService,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

import { definePosModels } from "../data/generate_model_definitions.js";
import { mountPosDialog, setupPosEnv } from "../utils.js";

definePosModels();

const mountClosingPopup = async (pos, refusal) => {
    pos.config.cash_control = false;
    const calls = [];
    patchWithCleanup(pos, { pushOrdersWithClosingPopup: async () => true });
    const navigations = [];
    patchWithCleanup(pos.router, { close: () => navigations.push("close") });
    patchWithCleanup(pos.data, {
        async call(_model, method) {
            calls.push(method);
            if (method === "update_closing_control_state_session") {
                return refusal;
            }
            return { successful: true };
        },
    });
    const popup = await mountPosDialog(ClosePosPopup, {
        orders_details: { quantity: 0, amount: 0 },
        opening_notes: "",
        default_cash_details: { id: 0, name: "", amount: 0, opening: 0, moves: [] },
        non_cash_payment_methods: [],
        is_manager: true,
        amount_authorized_diff: null,
        close: () => {},
    });
    return { popup, calls, navigations };
};

test("a refused closing state stops the close and shows why", async () => {
    mockService("report", () => ({ doAction: async () => {} }));
    const pos = await setupPosEnv();
    const { popup, calls, navigations } = await mountClosingPopup(pos, {
        successful: false,
        message: "Draft orders remain",
        redirect: false,
        open_order_ids: [],
    });

    await popup.closeSession();
    await animationFrame();

    expect(calls).toEqual(["update_closing_control_state_session"]);
    expect(".modal:contains(Draft orders remain)").toHaveCount(1);
    expect(navigations).toEqual([]);
});

test("an accepted closing state goes on to close the session", async () => {
    mockService("report", () => ({ doAction: async () => {} }));
    const pos = await setupPosEnv();
    const { popup, calls, navigations } = await mountClosingPopup(pos, true);

    await popup.closeSession();
    await animationFrame();

    expect(calls).toEqual([
        "update_closing_control_state_session",
        "close_session_from_ui",
    ]);
    expect(navigations).toEqual(["close"]);
});

test("an already closed session is reported in an alert and left only once it is read", async () => {
    mockService("report", () => ({ doAction: async () => {} }));
    const pos = await setupPosEnv();
    const { popup, navigations } = await mountClosingPopup(pos, {
        successful: false,
        type: "alert",
        title: "Session already closed",
        message: "The session has already been closed by another user.",
        redirect: true,
    });

    await popup.closeSession();
    await animationFrame();

    expect(".modal-title:contains(Session already closed)").toHaveCount(1);
    expect(".modal button:contains(Review Orders)").toHaveCount(0);
    expect(".modal button:contains(Cancel Orders)").toHaveCount(0);
    expect(navigations).toEqual([]);

    await contains(
        ".modal:has(.modal-title:contains(Session already closed)) .modal-footer .btn-primary",
    ).click();

    expect(navigations).toEqual(["close"]);
});
