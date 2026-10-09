// @ts-check

import "@proof/password_proof/password_proof";
import "@proof/proof_button/proof_button";
import "@proof/proof_service";

import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

class Handover extends models.Model {
    _name = "handover";
    name = fields.Char();

    _records = [{ id: 1, name: "DH/2026/00001" }];
}

defineModels([Handover]);

const params = {
    token: "challenge-token",
    expires: "",
    summary: [["Documents", "Deed 1"]],
    signer: "Notary Lopez",
    methods: [{ code: "password", name: "Password", options: {} }],
};

test("the button asks for the proof its record issues and hands it back", async () => {
    onRpc("handover", "action_issue_custodian_proof", ({ args }) => {
        expect.step(["issue", args[0]]);
        return params;
    });
    onRpc("handover", "action_prove_custodian", ({ args }) => {
        expect.step(["submit", args[0], args[1]]);
        return false;
    });
    await mountView({
        type: "form",
        resModel: "handover",
        resId: 1,
        arch: `
            <form>
                <field name="name"/>
                <widget name="proof_button" string="Custodian's Code"
                    issue="action_issue_custodian_proof" submit="action_prove_custodian"/>
            </form>`,
    });

    expect(".o_proof_button").toHaveText("Custodian's Code");
    await contains(".o_proof_button").click();
    await animationFrame();
    expect(".modal-title").toHaveText("Confirm it is Notary Lopez");
    await contains(".o_proof_password input").edit("1234", { confirm: false });
    await contains(".o_proof_password button[type=submit]").click();

    expect.verifySteps([
        ["issue", [1]],
        [
            "submit",
            [1],
            {
                token: "challenge-token",
                method: "password",
                payload: { password: "1234" },
            },
        ],
    ]);
    expect(".modal").toHaveCount(0);
});

test("nothing is asked when the record issues no proof", async () => {
    onRpc("handover", "action_issue_custodian_proof", () => false);
    await mountView({
        type: "form",
        resModel: "handover",
        resId: 1,
        arch: `
            <form>
                <widget name="proof_button" string="Custodian's Code"
                    issue="action_issue_custodian_proof" submit="action_prove_custodian"/>
            </form>`,
    });

    await contains(".o_proof_button").click();
    await animationFrame();

    expect(".modal").toHaveCount(0);
});
