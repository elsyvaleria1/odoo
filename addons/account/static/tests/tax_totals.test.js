import { describe, expect, test } from "@odoo/hoot";
import { queryOne } from "@odoo/hoot-dom";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

/** @param {number} taxAmount */
function totals(taxAmount) {
    return {
        currency_id: 1,
        currency_pd: 2,
        has_tax_groups: true,
        total_amount_currency: 100 + taxAmount,
        tax_amount_currency: taxAmount,
        subtotals: [
            {
                name: "Untaxed Amount",
                base_amount_currency: 100,
                tax_amount_currency: taxAmount,
                tax_groups: [
                    {
                        id: 1,
                        group_name: "Tax 15%",
                        tax_amount_currency: taxAmount,
                        base_amount_currency: 100,
                    },
                ],
            },
        ],
    };
}

/** @param {number} taxAmount */
function manualTotals(taxAmount, computedAmount) {
    const values = totals(taxAmount);
    Object.assign(values.subtotals[0].tax_groups[0], {
        manual_tax_amount: true,
        computed_tax_amount_currency: computedAmount,
    });
    return values;
}

class Move extends models.Model {
    _name = "move";

    tax_totals = fields.Json();

    _records = [
        { id: 1, tax_totals: totals(15) },
        { id: 2, tax_totals: manualTotals(16, 15) },
    ];
}

defineModels([Move]);

const ARCH = `
    <form>
        <field name="tax_totals" widget="account-tax-totals-field"/>
    </form>`;

async function editTaxGroup(value) {
    await contains(".o_tax_group_edit").click();
    await contains(".o_tax_group_edit_input input").edit(value);
}

describe("TaxTotalsComponent rendering", () => {
    test("shows the subtotal, the tax group and the total", async () => {
        await mountView({ type: "form", resModel: "move", resId: 1, arch: ARCH });

        expect("[name='Untaxed Amount']").toHaveText("$ 100.00");
        expect(".o_tax_total_label:contains(Tax 15%)").toHaveCount(1);
        expect("[name='amount_total']").toHaveText("$ 115.00");
    });
});

describe("TaxTotalsComponent editing", () => {
    test("writes the group, its subtotal and the total together", async () => {
        onRpc("move", "web_save", ({ args }) => {
            const written = args[1].tax_totals;
            expect.step("web_save");
            expect(written.subtotals[0].tax_groups[0].tax_amount_currency).toBe(20);
            expect(written.subtotals[0].tax_amount_currency).toBe(20);
            expect(written.tax_amount_currency).toBe(20);
            expect(written.total_amount_currency).toBe(120);
        });
        await mountView({ type: "form", resModel: "move", resId: 1, arch: ARCH });

        await editTaxGroup("20");
        await contains(".o_form_button_save").click();

        await expect.waitForSteps(["web_save"]);
    });

    test("accepts zero, which the server applies like any other amount", async () => {
        onRpc("move", "web_save", ({ args }) => {
            expect.step("web_save");
            expect(
                args[1].tax_totals.subtotals[0].tax_groups[0].tax_amount_currency,
            ).toBe(0);
            expect(args[1].tax_totals.total_amount_currency).toBe(100);
        });
        await mountView({ type: "form", resModel: "move", resId: 1, arch: ARCH });

        await editTaxGroup("0");
        await contains(".o_form_button_save").click();

        await expect.waitForSteps(["web_save"]);
    });

    test("keeps the record untouched when the amount is unchanged", async () => {
        onRpc("move", "web_save", () => expect.step("web_save"));
        await mountView({ type: "form", resModel: "move", resId: 1, arch: ARCH });

        await editTaxGroup("15");

        expect(".o_form_status_indicator_buttons").toHaveClass("invisible");
        await expect.waitForSteps([]);
    });

    test("restores the formatted amount when the input cannot be parsed", async () => {
        await mountView({ type: "form", resModel: "move", resId: 1, arch: ARCH });

        await editTaxGroup("not a number");

        expect(queryOne(".o_tax_group_edit_input input").value).toBe("15.00");
    });
});

describe("TaxTotalsComponent manual amounts", () => {
    test("marks a manual group and offers no reset on a computed one", async () => {
        await mountView({ type: "form", resModel: "move", resId: 1, arch: ARCH });
        expect(".o_tax_group_manual").toHaveCount(0);
        expect(".o_tax_group_reset").toHaveCount(0);
    });

    test("shows the badge with the computed amount", async () => {
        await mountView({ type: "form", resModel: "move", resId: 2, arch: ARCH });
        expect(".o_tax_group_manual").toHaveText("manual");
        expect(queryOne(".o_tax_group_manual").title).toMatch(
            /^Typed by hand; computed: \$\s15\.00$/,
        );
    });

    test("reset writes the computed amount back", async () => {
        onRpc("move", "web_save", ({ args }) => {
            expect.step("web_save");
            expect(
                args[1].tax_totals.subtotals[0].tax_groups[0].tax_amount_currency,
            ).toBe(15);
            expect(args[1].tax_totals.total_amount_currency).toBe(115);
        });
        await mountView({ type: "form", resModel: "move", resId: 2, arch: ARCH });

        await contains(".o_tax_group_reset").click();
        await contains(".o_form_button_save").click();

        await expect.waitForSteps(["web_save"]);
    });
});
