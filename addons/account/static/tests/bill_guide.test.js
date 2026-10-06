import { openFormView, start, startServer } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { defineModels, models, onRpc } from "@web/../tests/web_test_helpers";

import { defineAccountModels } from "./account_test_helpers.js";

describe.current.tags("desktop");

class MailAlias extends models.ServerModel {
    _name = "mail.alias";
}

defineAccountModels();
defineModels({ MailAlias });

const ARCH = `
    <form>
        <field name="type" invisible="1"/>
        <field name="alias_email" invisible="1"/>
        <widget name="bill_upload_guide"/>
    </form>`;

describe("BillGuide alias", () => {
    test("links to the journal alias when the journal has one", async () => {
        const pyEnv = await startServer();
        const aliasId = pyEnv["mail.alias"].create({
            alias_full_name: "bills@test.example.com",
        });
        const journalId = pyEnv["account.journal"].create({
            name: "Vendor Bills",
            type: "purchase",
            alias_id: aliasId,
        });
        await start();

        await openFormView("account.journal", journalId, { arch: ARCH });

        expect("a[href^='mailto:']").toHaveCount(1);
        expect("a[href^='mailto:']").toHaveText("bills@test.example.com");
        expect(".o_invoice_new").toHaveCount(0);
    });

    test("falls back to manual creation when the journal has no alias", async () => {
        const pyEnv = await startServer();
        const journalId = pyEnv["account.journal"].create({
            name: "Vendor Bills",
            type: "purchase",
        });
        await start();

        await openFormView("account.journal", journalId, { arch: ARCH });

        expect("a[href^='mailto:']").toHaveCount(0);
        expect(".o_invoice_new").toHaveCount(1);
    });
});

describe("BillGuide sample action", () => {
    const DASHBOARD_ARCH = `
        <form>
            <field name="type" invisible="1"/>
            <field name="alias_email" invisible="1"/>
            <field name="kanban_dashboard" invisible="1"/>
            <widget name="bill_upload_guide"/>
        </form>`;

    test("a dashboard card reads it from its own data, without a call", async () => {
        const pyEnv = await startServer();
        const journalId = pyEnv["account.journal"].create({
            name: "Vendor Bills",
            type: "purchase",
            kanban_dashboard: JSON.stringify({ sample_action_available: true }),
        });
        onRpc("account.journal", "is_sample_action_available", () => {
            expect.step("is_sample_action_available");
            return false;
        });
        await start();

        await openFormView("account.journal", journalId, { arch: DASHBOARD_ARCH });

        expect("a[name='action_create_vendor_bill']").toHaveCount(1);
        expect.verifySteps([]);
    });

    test("without dashboard data it asks the server", async () => {
        const pyEnv = await startServer();
        const journalId = pyEnv["account.journal"].create({
            name: "Vendor Bills",
            type: "purchase",
        });
        onRpc("account.journal", "is_sample_action_available", () => {
            expect.step("is_sample_action_available");
            return true;
        });
        await start();

        await openFormView("account.journal", journalId, { arch: ARCH });

        expect("a[name='action_create_vendor_bill']").toHaveCount(1);
        expect.verifySteps(["is_sample_action_available"]);
    });
});
