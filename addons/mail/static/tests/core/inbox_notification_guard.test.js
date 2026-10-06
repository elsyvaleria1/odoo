// @ts-check
import { defineMailModels, start, startServer } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { getService, serverState } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("a needaction notification whose message is absent from store_data still counts", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    await start();
    const store = getService("mail.store");
    await store.isReady;
    const before = store.needaction_counter;
    const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
    pyEnv["bus.bus"]._sendone(partner, "mail.message/needaction", {
        message_id: 4242,
        needaction_delta: 1,
        store_data: {},
    });
    await waitUntil(() => store.needaction_counter === before + 1);
    expect(store["mail.message"].get(4242)).toBe(undefined);
    expect(store.messagingMenu.notificationTab.messages).toHaveLength(0);
});
