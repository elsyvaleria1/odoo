import { AccountPaymentField } from "@account/components/account_payment_field/account_payment_field";
import { describe, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { mountWithCleanup, onRpc } from "@web/../tests/web_test_helpers";

import { defineAccountModels } from "./account_test_helpers.js";

defineAccountModels();

describe.current.tags("desktop");

function record(content) {
    return {
        resId: 7,
        resModel: "account.move",
        data: {
            invoice_payments_widget: {
                title: "Less Payment",
                outstanding: false,
                content,
            },
        },
        model: { root: { load: async () => {} } },
    };
}

const pendingEntry = {
    name: "SPEI ENVIADO",
    journal_name: "Bank",
    amount: 2721.22,
    currency_id: 1,
    date: "2026-10-03",
    partial_id: false,
    pending_match_id: 42,
    is_pending: true,
    move_id: 11,
    ref: "BNC1/2026/10/0001",
    is_exchange: false,
    amount_company_currency: "$ 2,721.22",
    amount_foreign_currency: false,
};

test("a pending match reads as matched, pending posting", async () => {
    await mountWithCleanup(AccountPaymentField, {
        props: { name: "invoice_payments_widget", record: record([pendingEntry]) },
    });

    expect(".o_payment_label").toHaveText("Matched, pending posting, on 10/03/2026");
});

test("a paid entry still reads as paid", async () => {
    await mountWithCleanup(AccountPaymentField, {
        props: {
            name: "invoice_payments_widget",
            record: record([
                {
                    ...pendingEntry,
                    is_pending: false,
                    pending_match_id: false,
                    partial_id: 5,
                },
            ]),
        },
    });

    expect(".o_payment_label").toHaveText("Paid on 10/03/2026");
});

test("unreconciling a pending match removes the pending match", async () => {
    const calls = [];
    onRpc("account.move", "js_remove_pending_match", ({ args }) => {
        calls.push(["js_remove_pending_match", args]);
        return true;
    });
    onRpc("account.move", "js_remove_outstanding_partial", ({ args }) => {
        calls.push(["js_remove_outstanding_partial", args]);
        return true;
    });
    await mountWithCleanup(AccountPaymentField, {
        props: { name: "invoice_payments_widget", record: record([pendingEntry]) },
    });

    await click(".js_payment_info");
    await animationFrame();
    await click(".js_unreconcile_payment");
    await animationFrame();

    expect(calls).toEqual([["js_remove_pending_match", [7, 42]]]);
});
