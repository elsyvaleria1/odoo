// @ts-check
import {
    click,
    contains,
    defineMailModels,
    start,
    startServer,
    triggerHotkey,
} from "@mail/../tests/mail_test_helpers";
import { ActivityMenu } from "@mail/core/web/activity_menu";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, queryText } from "@odoo/hoot-dom";
import {
    getService,
    mountWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("should update activities when opening the activity menu", async () => {
    const pyEnv = await startServer();
    await start();
    await contains(".o_menu_systray i[aria-label='Activities']");
    await contains(".o-mail-ActivityMenu-counter", { count: 0 });
    const partnerId = pyEnv["res.partner"].create({});
    pyEnv["mail.activity"].create({
        res_id: partnerId,
        res_model: "res.partner",
    });
    await click(".o_menu_systray i[aria-label='Activities']");
    await contains(".o-mail-ActivityMenu-counter", { text: "1" });
});

test("activity counter: a systray answer older than an applied notification does not undo it", async () => {
    const pyEnv = await startServer();
    await start();
    const store = getService("mail.store");
    await contains(".o_menu_systray i[aria-label='Activities']");
    const baseCounter = store.activityCounter;
    const snapshotBusId = pyEnv["bus.bus"].lastBusNotificationId;
    const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
    pyEnv["bus.bus"]._sendone(partner, "mail.activity/updated", {
        activity_created: true,
        count_diff: 1,
    });
    await contains(".o-mail-ActivityMenu-counter", { text: String(baseCounter + 1) });
    // a systray answer computed before that notification was sent
    store.insert({
        Store: { activityCounter: baseCounter, activityCounter_bus_id: snapshotBusId },
    });
    expect(store.activityCounter).toBe(baseCounter + 1);
    const freshBusId = pyEnv["bus.bus"].lastBusNotificationId;
    store.insert({
        Store: { activityCounter: baseCounter + 3, activityCounter_bus_id: freshBusId },
    });
    expect(store.activityCounter).toBe(baseCounter + 3);
    store.insert({
        Store: { activityCounter: baseCounter, activityCounter_bus_id: snapshotBusId },
    });
    expect(store.activityCounter).toBe(baseCounter + 3);
    expect(store.activityCounter_bus_id).toBe(freshBusId);
});

test("global shortcut", async () => {
    await mountWithCleanup(ActivityMenu);
    await triggerHotkey("control+k");
    await animationFrame();
    expect(queryText(`.o_command:contains("Activity") .o_command_hotkey`)).toEqual(
        "Activity\nALT + SHIFT + A",
        { message: "The command should be registered with the right hotkey" },
    );
    await triggerHotkey("alt+shift+a");
    await animationFrame();
    expect(".modal-dialog .modal-title").toHaveText("Schedule Activity");
});
