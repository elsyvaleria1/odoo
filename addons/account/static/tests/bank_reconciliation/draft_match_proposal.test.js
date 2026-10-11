import { BankRecDraftMatchProposal } from "@account/components/bank_reconciliation/draft_match_proposal/draft_match_proposal";
import { getReconciledLineName } from "@account/components/bank_reconciliation/statement_line/statement_line";
import { mailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { defineModels, mountWithCleanup } from "@web/../tests/web_test_helpers";

defineModels(mailModels);

describe.current.tags("desktop");

test("a proposal names the draft and offers to match or dismiss it", async () => {
    const calls = [];
    await mountWithCleanup(BankRecDraftMatchProposal, {
        props: {
            label: "BILL/2026/10/0001",
            onConfirm: () => calls.push("confirm"),
            onDismiss: () => calls.push("dismiss"),
        },
    });

    expect("[name=draft_match_proposal_label]").toHaveText("BILL/2026/10/0001");
    await click(".o_confirm_draft_match");
    await click(".o_dismiss_draft_match");
    await animationFrame();
    expect(calls).toEqual(["confirm", "dismiss"]);
});

function line({
    reconciled = [],
    pending = false,
    taxes = [],
    account = "401 Payables",
}) {
    return {
        reconciled_lines_excluding_exchange_diff_ids: {
            records: reconciled.map((name) => ({ data: { move_name: name } })),
        },
        pending_match_label: pending,
        tax_ids: { count: taxes.length, records: taxes },
        account_id: { display_name: account },
    };
}

test("a line matched to one entry is named after it", () => {
    expect(getReconciledLineName(line({ reconciled: ["INV/1"] }))).toEqual({
        move: "INV/1",
    });
});

test("a line pending a draft's posting is named after the draft", () => {
    expect(
        getReconciledLineName(line({ pending: "BILL/7 (pending posting)" })),
    ).toEqual({ move: "BILL/7 (pending posting)" });
});

test("a reconciliation outranks a pending match, a pending match outranks the account", () => {
    expect(
        getReconciledLineName(line({ reconciled: ["INV/1"], pending: "BILL/7" })),
    ).toEqual({ move: "INV/1" });
    expect(getReconciledLineName(line({}))).toEqual({ account: "401 Payables" });
});
