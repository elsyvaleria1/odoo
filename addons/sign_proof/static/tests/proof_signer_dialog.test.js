import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { click, waitFor } from "@odoo/hoot-dom";
import { fakeSignInfoService } from "@sign/../tests/dialog/dialog_utils";
import { ProofSignerDialog } from "@sign_proof/dialogs/proof_signer_dialog";
import {
    contains,
    makeDialogMockEnv,
    mockService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";

const documentId = 23;
const signRequestItemToken = "abc";

beforeEach(() => {
    mockService("signInfo", fakeSignInfoService({ documentId, signRequestItemToken }));
});

describe.current.tags("desktop");
defineMailModels();

const mountDialog = async (postValidation) => {
    await makeDialogMockEnv();
    await mountWithCleanup(ProofSignerDialog, {
        props: { postValidation, close: () => {} },
    });
};

test("the signer asks for the code and signs with it", async () => {
    onRpc(`/sign/proof/${documentId}/${signRequestItemToken}`, () => {
        expect.step("code-sent");
        return { token: "tok", method: "email_code", sent_to: "l*****@example.com" };
    });
    await mountDialog((proof) => {
        expect.step("post-validation");
        expect(proof).toEqual({ token: "tok", method: "email_code", code: "123456" });
    });
    expect(".o_sign_proof_validate").not.toBeEnabled();

    await click(".o_sign_proof_send");
    await waitFor("p:contains('l*****@example.com')");
    expect.verifySteps(["code-sent"]);
    await contains(".o_sign_proof_code").edit("123456", { confirm: false });
    await click(".o_sign_proof_validate");
    expect.verifySteps(["post-validation"]);
});

test("a refusal to send the code is shown and nothing is signed", async () => {
    onRpc(`/sign/proof/${documentId}/${signRequestItemToken}`, () => ({
        error: "Ferreteria Lupita has no way set up to prove it is them.",
    }));
    await mountDialog(() => expect.step("post-validation"));

    await click(".o_sign_proof_send");
    await waitFor(".alert-warning:contains('no way set up')");

    expect(".o_sign_proof_validate").not.toBeEnabled();
    expect.verifySteps([]);
});
