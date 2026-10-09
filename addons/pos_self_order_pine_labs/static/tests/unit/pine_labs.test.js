import { expect, test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-mock";
import { PineLabs } from "@pos_self_order_pine_labs/app/pine_labs";
import { makeMockEnv, onRpc } from "@web/../tests/web_test_helpers";

const STATUS = "/pos-self-order/pine-labs-fetch-payment-status/";
const CANCEL = "/pos-self-order/pine-labs-cancel-transaction/";
const ORDER = {
    id: 7,
    amount_total: 10,
    currency: { toMinorUnits: (amount) => Math.round(amount * 100) },
};

const answering = (answers) => {
    const calls = [];
    return {
        calls,
        handler: () => {
            const answer = answers[calls.length];
            calls.push(answer);
            if (!answer) {
                throw new Error("the kiosk lost the server");
            }
            return answer;
        },
    };
};

const makePineLabs = async () => {
    await makeMockEnv();
    const errors = [];
    const pineLabs = new PineLabs({ id: 1 }, "token", { id: 1 }, (error) =>
        errors.push(error),
    );
    return { pineLabs, errors };
};

test("a lost or unknown status is no failure: the kiosk keeps polling", async () => {
    const status = answering([
        null,
        { outcome: "unknown", error: "TXN NOT FOUND" },
        { outcome: "approved" },
    ]);
    onRpc(STATUS, status.handler);
    const { pineLabs, errors } = await makePineLabs();

    const polling = pineLabs.paymentPolling(ORDER);
    await advanceTime(5000);
    await advanceTime(5000);

    expect(await polling).toBe(true);
    expect(status.calls).toHaveLength(3);
    expect(errors).toEqual([]);
});

test("an unanswered cancellation is asked again, never offered as Retry", async () => {
    const cancel = answering([
        null,
        { outcome: "unverified", error: "TXN IN PROGRESS" },
    ]);
    onRpc(CANCEL, cancel.handler);
    const { pineLabs, errors } = await makePineLabs();

    const cancelled = pineLabs.cancelPayment(ORDER);
    await advanceTime(5000);

    expect(await cancelled).toBe(false);
    expect(cancel.calls).toHaveLength(2);
    expect(errors).toEqual([]);
});

test("a cancelled transaction lets the customer pay again", async () => {
    onRpc(CANCEL, () => ({ outcome: "failed", notification: "Cancelled" }));
    const { pineLabs, errors } = await makePineLabs();

    expect(await pineLabs.cancelPayment(ORDER)).toBe(true);
    expect(errors).toHaveLength(1);
});
