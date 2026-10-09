import { expect, test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-mock";
import { Razorpay } from "@pos_self_order_razorpay/app/razorpay";
import { makeMockEnv, onRpc } from "@web/../tests/web_test_helpers";

const STATUS = "/pos-self-order/razorpay-fetch-payment-status/";
const CANCEL = "/pos-self-order/razorpay-cancel-transaction/";

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

const makeRazorpay = async () => {
    const env = await makeMockEnv();
    const errors = [];
    const razorpay = new Razorpay(env, { id: 1 }, "token", { id: 1 }, (error) =>
        errors.push(error),
    );
    return { razorpay, errors };
};

test("a lost or unknown status is no failure: the kiosk keeps polling", async () => {
    const status = answering([null, { outcome: "unknown" }, { outcome: "approved" }]);
    onRpc(STATUS, status.handler);
    const { razorpay, errors } = await makeRazorpay();

    await razorpay.paymentPolling({ id: 7 });
    await advanceTime(10000);
    await advanceTime(10000);

    expect(status.calls).toHaveLength(3);
    expect(errors).toEqual([]);
});

test("an unanswered cancellation is asked again, never offered as Retry", async () => {
    const cancel = answering([null, { outcome: "unverified" }]);
    onRpc(CANCEL, cancel.handler);
    const { razorpay, errors } = await makeRazorpay();

    const cancelled = razorpay.cancelPayment({ id: 7 });
    await advanceTime(10000);

    expect(await cancelled).toBe(false);
    expect(cancel.calls).toHaveLength(2);
    expect(errors).toEqual([]);
});

test("a failed transaction lets the customer pay again", async () => {
    onRpc(STATUS, () => ({ outcome: "failed", error: "Card declined" }));
    const { razorpay, errors } = await makeRazorpay();

    await razorpay.paymentPolling({ id: 7 });

    expect(errors).toHaveLength(1);
});
