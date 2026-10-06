// @ts-check
import { JournalsTile } from "@account/components/home_tile/journals_tile";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    mockService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

const DATA = {
    to_reconcile: 4,
    to_validate: 2,
    late: 1,
    journals: [
        {
            id: 1,
            name: "Customer Invoices",
            type: "sale",
            to_reconcile: 0,
            to_validate: 2,
            late: 1,
        },
        { id: 2, name: "Bank", type: "bank", to_reconcile: 4, to_validate: 0, late: 0 },
    ],
};

test("the accounting tile totals the journals and opens what waits in one", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(typeof action === "string" ? action : action.name);
        },
    });
    onRpc("account.journal", "open_action", ({ args, kwargs }) => {
        const set = Object.fromEntries(
            Object.entries(kwargs.context).filter(
                ([key]) => key.startsWith("search_default_") || key === "journal_type",
            ),
        );
        expect.step(`open ${args[0]} ${JSON.stringify(set)}`);
        return { name: `journal ${args[0]}` };
    });
    await mountWithCleanup(JournalsTile, { props: { data: DATA, size: "1x1" } });
    expect(queryAllTexts(".o_journals_tile_totals strong")).toEqual(["4", "2", "1"]);

    await contains(".o_journals_tile_journal:first").click();
    await contains(".o_journals_tile_journal:last").click();
    await contains(".o_journals_tile_totals").click();
    expect.verifySteps([
        'open 1 {"search_default_late":"1","search_default_posted":"1","journal_type":"sale"}',
        "journal 1",
        "open 2 {}",
        "journal 2",
        "account.open_account_journal_dashboard_kanban",
    ]);
});

test("journals with nothing waiting say so", async () => {
    await mountWithCleanup(JournalsTile, {
        props: {
            data: { to_reconcile: 0, to_validate: 0, late: 0, journals: [] },
            size: "1x1",
        },
    });
    expect(".o_journals_tile p").toHaveText("Every journal is up to date.");
});
