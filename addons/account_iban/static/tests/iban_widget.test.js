/** @odoo-module native */
import { DELAY } from "@account_iban/components/iban_widget/iban_widget";
import {
    click,
    contains,
    insertText,
    openFormView,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-mock";
import { onRpc } from "@web/../tests/web_test_helpers";

import { defineAccountIbanModels } from "./account_iban_test_helpers.js";

defineAccountIbanModels();

const validIban = "BE12651194580992";
const invalidIban = "invalidIban!";

test.tags("focus required");
test("Iban Widget full flow", async () => {
    const pyEnv = await startServer();
    const bankId = pyEnv["res.partner.bank.account"].create({ acc_number: "" });
    const partnerId = pyEnv["res.partner"].create({
        name: "Awesome partner",
        bank_account_ids: [bankId],
    });
    await start();
    onRpc("res.partner.bank.account", "is_valid_iban", (params) => {
        const iban = params.args[1].replace(/\s/g, "");
        return iban === validIban;
    });
    await openFormView("res.partner", partnerId, {
        arch: `<form>
                <sheet>
                    <group>
                        <field name="name"/>
                    </group>
                    <field name="bank_account_ids">
                        <list editable="bottom">
                            <field name="acc_number" widget="iban"/>
                        </list>
                    </field>
                </sheet>
            </form>`,
    });
    await contains("td.o_iban_cell");
    await contains(".o_iban", { count: 0 });
    await click("td.o_iban_cell");
    await contains(".o_iban_input_with_validator");
    await contains(".o_iban", { count: 0 });
    await insertText(".o_iban_input_with_validator", invalidIban, { replace: true });
    await contains(".o_iban", { count: 0 });
    await advanceTime(DELAY);
    await contains(".o_iban");
    await contains("i.fa-solid.fa-times.o_iban_fail");
    await contains("i.fa-solid.fa-check.o_iban", { count: 0 });
    await click(".o_form_button_save");
    await contains(".o_iban", { count: 0 });
    await click("td.o_iban_cell");
    await contains(".o_iban_input_with_validator");
    await advanceTime(DELAY);
    await contains("i.fa-solid.fa-times.o_iban_fail");
    await insertText(".o_iban_cell .o_input", validIban, { replace: true });
    await contains("i.fa-solid.fa-times.o_iban_fail");
    await advanceTime(DELAY);
    await contains(".o_iban");
    await contains("i.fa-solid.fa-check.o_iban");
    await contains("i.fa-solid.fa-times.o_iban_fail", { count: 0 });
    await click(".o_form_button_save");
    await contains(".o_iban", { count: 0 });
});
