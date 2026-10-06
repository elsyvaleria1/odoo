import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { ThankYouDialog } from "@sign/dialogs/dialogs";
import {
    makeDialogMockEnv,
    mockService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { session } from "@web/session";

import { fakeSignInfoService } from "./dialog_utils.js";

const createEnv = async () => await makeDialogMockEnv();

const mountThankYouDialog = async (additionalProps = {}) =>
    mountWithCleanup(ThankYouDialog, {
        props: {
            message: "bla",
            subtitle: "aha",
            close: () => {},
            ...additionalProps,
        },
    });

const signInfo = {
    documentId: 23,
    signRequestToken: "abc",
};

// Inside the hook, not at module scope: HOOT imports every test file at
// collection, and a module-scope mock is the last file's for every suite.
beforeEach(() => {
    mockService("signInfo", fakeSignInfoService(signInfo));
});

describe.current.tags("desktop");
defineMailModels();

beforeEach(() => {
    onRpc("/sign/sign_request_state/23/abc", () => "draft");
    onRpc("/sign/sign_request_items", () => []);
    onRpc("sign.request", "get_close_values", () => ({
        label: "Close",
        action: {
            type: "ir.actions.act_window",
            res_model: "sign_request",
            views: [[false, "kanban"]],
        },
    }));
});

test("Thank you dialog is correctly rendered", async () => {
    await createEnv();
    await mountThankYouDialog();

    expect(".modal-title").toHaveText("It's signed!");
    expect("#thank-you-message").toHaveText("bla", {
        message: "Should render message",
    });
    expect("#thank-you-subtitle").toHaveText("aha", {
        message: "Should render subtitle",
    });
});

test("suggest signup is shown", async () => {
    patchWithCleanup(user, { userId: false });
    await createEnv();
    await mountThankYouDialog();

    expect("a:contains('Odoo Sign')").toHaveCount(1, {
        message: "Should render sign up link",
    });
});

test("download button is shown when document is completed", async () => {
    onRpc("/sign/sign_request_state/23/abc", () => "signed");
    await createEnv();
    await mountThankYouDialog();

    expect("button:contains('Download')").toHaveCount(1, {
        message: "Should render download document button",
    });
});

test("redirect button works", async () => {
    onRpc("/sign/sign_request_state/23/abc", () => "signed");
    await createEnv();
    await mountThankYouDialog({
        redirectURL: "https://shorturl.at/jnxMP",
        redirectURLText: "Redirect Button",
    });

    expect(".o_sign_thankyou_redirect_button").toHaveText("Redirect Button", {
        message: "Should render redirect button when redirectURL is passed as props",
    });
    expect("button:contains('Download')").toHaveCount(1, {
        message: "Should render download document button",
    });
});

test("renders on the public signing page, which has no action service", async () => {
    registry.category("services").remove("action");
    patchWithCleanup(session, { is_frontend: true });
    await createEnv();
    await mountThankYouDialog();

    expect(".modal-title").toHaveText("It's signed!");
    expect("#thank-you-message").toHaveText("bla");
});
