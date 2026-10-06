import { expect, test } from "@odoo/hoot";
import {
    mountWebClient,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { SysAdminPanel } from "@web/webclient/home_menu/sysadmin_panel";

/**
 * @param {Object} params
 * @param {boolean} params.admin
 * @param {string} [params.audience]
 * @param {string} [params.message]
 */
function withMessage({ admin, audience, message }) {
    patchWithCleanup(user, { isSystem: admin });
    patchWithCleanup(session, {
        sysadmin_message: { message, warning_type: audience },
    });
}

test("no panel when the message names no audience", async () => {
    withMessage({ admin: true, audience: undefined, message: "hello" });
    await mountWithCleanup(SysAdminPanel);
    expect(".o_sysadmin_message").toHaveText("");
});

test("a message aimed at users is shown to a non-admin reader", async () => {
    withMessage({ admin: false, audience: "user", message: "scheduled downtime" });
    await mountWithCleanup(SysAdminPanel);
    expect(".o_sysadmin_message").toHaveText("scheduled downtime");
});

test("a message aimed at admins is hidden from a non-admin reader", async () => {
    withMessage({ admin: false, audience: "admin", message: "admins only" });
    await mountWithCleanup(SysAdminPanel);
    expect(".o_sysadmin_message").toHaveText("");
});

test("a message aimed at admins is shown to an admin reader", async () => {
    withMessage({ admin: true, audience: "admin", message: "admins only" });
    await mountWithCleanup(SysAdminPanel);
    expect(".o_sysadmin_message").toHaveText("admins only");
});

test("an audience the client does not recognise is hidden from everyone", async () => {
    withMessage({ admin: true, audience: "everyone", message: "who knows" });
    await mountWithCleanup(SysAdminPanel);
    expect(".o_sysadmin_message").toHaveText("");
});

test("markup in the message renders as HTML, not as visible markup", async () => {
    withMessage({ admin: false, audience: "user", message: "<b>maintenance</b>" });
    await mountWithCleanup(SysAdminPanel);
    expect(".o_sysadmin_message b").toHaveText("maintenance");
});

test("the home menu shows the message in its banner stack, and nothing blocks the page", async () => {
    withMessage({ admin: false, audience: "user", message: "scheduled downtime" });
    await mountWebClient();
    expect(".o_home_menu .o_sysadmin_message").toHaveText("scheduled downtime");
    expect(".o_expired_subscription_overlay").toHaveCount(0);
});

test("without a message the home menu shows no sysadmin banner", async () => {
    patchWithCleanup(session, { sysadmin_message: undefined });
    await mountWebClient();
    expect(".o_home_menu").toHaveCount(1);
    expect(".o_sysadmin_message").toHaveCount(0);
});
