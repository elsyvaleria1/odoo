import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { click, edit } from "@odoo/hoot-dom";
import {
    defineModels,
    fields,
    models,
    mountView,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

class WizardPaymentTransactionViewLink extends models.Model {
    _name = "wizard.payment.transaction.view.link";

    amount = fields.Float({
        type: "float",
        onChange: (record) => {
            record.link = `/payment/pay?amount=${record.amount}`;
        },
    });
    link = fields.Char({ type: "char" });

    _records = [{ id: 1, amount: 15, link: "/payment/pay?amount=15" }];
}

defineModels([WizardPaymentTransactionViewLink]);
defineMailModels();

test("copy link immediatly after entering the amount", async () => {
    patchWithCleanup(navigator.clipboard, {
        async writeText(text) {
            expect.step(text);
        },
    });

    await mountView({
        type: "form",
        resModel: "wizard.payment.transaction.view.link",
        arch: `<form>
            <group>
                <group>
                    <field name="amount"/>
                     <field
                        string="Generate and Copy Payment Link"
                        name="link"
                        widget="PaymentWizardCopyClipboardButtonField"
                    />
                </group>
            </group>
        </form>`,
        resId: 1,
    });

    await click(".o_field_widget[name=amount] input");
    await edit("13");
    await click(".o_clipboard_button");
    expect.verifySteps(["/payment/pay?amount=13"]);
});
