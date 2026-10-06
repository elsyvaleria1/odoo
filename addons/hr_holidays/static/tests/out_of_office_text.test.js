import { defineHrHolidaysModels } from "@hr_holidays/../tests/hr_holidays_test_helpers";
import { getOutOfOfficeDateEndText } from "@hr_holidays/res_partner_model_patch";
import {
    click,
    contains,
    insertText,
    openDiscuss,
    openFormView,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { press } from "@odoo/hoot-dom";
import { mockDate, mockTimeZone } from "@odoo/hoot-mock";
import { Command, serverState } from "@web/../tests/web_test_helpers";
import { now, toISODate } from "@web/core/l10n/dates";

describe.current.tags("desktop");
defineHrHolidaysModels();

test("Show 'back on' in avatar card", async () => {
    mockDate("2025-04-08 12:00:00");
    const pyEnv = await startServer();
    const employee = pyEnv["hr.employee"].create({
        user_id: serverState.userId,
        partner_id: serverState.partnerId,
        leave_date_to: toISODate(now().add({ days: 3 })),
    });
    pyEnv["res.users"].write([serverState.userId], {
        employee_ids: [Command.link(employee)],
    });

    const fakeId = pyEnv["res.fake"].create({ name: "Salutations, voyageur" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "not empty",
        model: "res.fake",
        res_id: fakeId,
        subject: "Another Subject",
    });
    await start();
    await openFormView("res.fake", fakeId);
    await click(".o-mail-Message-avatar");
    await contains(".o_avatar_card span", { text: "Back on Apr 11" });
});

test("'back on' is the leave's own day west of UTC", async () => {
    mockDate("2025-04-08 12:00:00");
    mockTimeZone("America/New_York");
    const pyEnv = await startServer();
    const employee = pyEnv["hr.employee"].create({
        user_id: serverState.userId,
        partner_id: serverState.partnerId,
        leave_date_to: "2025-04-11",
    });
    pyEnv["res.users"].write([serverState.userId], {
        employee_ids: [Command.link(employee)],
    });
    const fakeId = pyEnv["res.fake"].create({ name: "Salutations, voyageur" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "not empty",
        model: "res.fake",
        res_id: fakeId,
        subject: "Another Subject",
    });
    await start();
    await openFormView("res.fake", fakeId);
    await click(".o-mail-Message-avatar");
    await contains(".o_avatar_card span", { text: "Back on Apr 11" });
});

test("a 'back on' date read from the server is not moved by the user's zone", () => {
    mockDate("2025-04-08 12:00:00");
    mockTimeZone("America/New_York");
    expect(getOutOfOfficeDateEndText("2025-04-11")).toBe("Back on Apr 11");
});

test("Show 'back on' in mention list", async () => {
    mockDate("2025-04-08 12:00:00");
    const pyEnv = await startServer();
    const employee = pyEnv["hr.employee"].create({
        user_id: serverState.userId,
        leave_date_to: toISODate(now().add({ days: 3 })),
    });
    pyEnv["res.users"].write([serverState.userId], {
        employee_ids: [Command.link(employee)],
    });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General & good",
        channel_member_ids: [Command.create({ partner_id: serverState.partnerId })],
    });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "@");
    await contains(".o-mail-NavigableList-item span", { text: "Back on Apr 11" });
});

test("Show year when 'back on' is on different year than now", async () => {
    mockDate("2024-12-20 12:00:00");
    const pyEnv = await startServer();
    const employee = pyEnv["hr.employee"].create({
        user_id: serverState.userId,
        partner_id: serverState.partnerId,
        leave_date_to: toISODate(now().add({ days: 15 })),
    });
    pyEnv["res.users"].write([serverState.userId], {
        employee_ids: [(6, 0, employee)],
    });
    const fakeId = pyEnv["res.fake"].create({ name: "Salutations, voyageur" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "not empty",
        model: "res.fake",
        res_id: fakeId,
        subject: "Another Subject",
    });
    await start();
    await openFormView("res.fake", fakeId);
    await click(".o-mail-Message-avatar");
    await contains(".o_avatar_card span", { text: "Back on Jan 4, 2025" });
});

test("Discuss chat item shows out of office indication", async () => {
    mockDate("2025-04-08 12:00:00");
    const pyEnv = await startServer();
    pyEnv["hr.employee"].create({
        user_id: serverState.userId,
        leave_date_to: toISODate(now().add({ days: 3 })),
    });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [Command.create({ partner_id: serverState.partnerId })],
        channel_type: "chat",
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-NotificationItem-name .text-warning", {
        text: "Back on Apr 11",
    });
});

test("CTRL+K command shows out of office indication", async () => {
    mockDate("2025-04-08 12:00:00");
    const pyEnv = await startServer();
    pyEnv["hr.employee"].create({
        user_id: serverState.userId,
        leave_date_to: toISODate(now().add({ days: 3 })),
    });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [Command.create({ partner_id: serverState.partnerId })],
        channel_type: "chat",
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Discuss[data-active]");
    await press(["ctrl", "k"]);
    await contains(".o-mail-DiscussCommand .text-warning", {
        text: "Back on Apr 11",
    });
});
