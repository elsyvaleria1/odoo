// @ts-check
import { defineMailModels, start, startServer } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { getService } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

async function countRecomputes(store, fn) {
    const Model = store.Thread._rawStore.Models.Store;
    const compute = Model._.fieldsCompute.get("globalCounter");
    let runs = 0;
    Model._.fieldsCompute.set("globalCounter", function () {
        runs++;
        return compute.call(this);
    });
    try {
        await fn();
    } finally {
        Model._.fieldsCompute.set("globalCounter", compute);
    }
    return runs;
}

test("threads with nothing pending do not recompute the global counter", async () => {
    await startServer();
    await start();
    const store = getService("mail.store");
    for (let i = 1; i <= 50; i++) {
        store["discuss.channel"].insert({ id: i, name: `chan ${i}` });
    }
    const runs = await countRecomputes(store, () => {
        for (let i = 51; i <= 60; i++) {
            store["discuss.channel"].insert({ id: i, name: `chan ${i}` });
        }
    });
    expect(runs).toBe(0, {
        message:
            "inserting channels with no unread/needaction must not touch the badge",
    });
});

test("a needaction on one channel does not re-read every other channel", async () => {
    await startServer();
    await start();
    const store = getService("mail.store");
    const channelTab = store.messagingMenu.channelTab;
    const threads = [];
    for (let i = 1; i <= 50; i++) {
        threads.push(
            store["discuss.channel"].insert({
                id: i,
                name: `chan ${i}`,
                channel_type: "channel",
            }),
        );
    }
    threads[0].message_needaction_counter = 1;
    expect(threads[0].in(channelTab.channelsWithCounter)).toBe(true);
    expect(threads[1].notIn(channelTab.channelsWithCounter)).toBe(true);
    threads[0].message_needaction_counter = 0;
    expect(threads[0].notIn(channelTab.channelsWithCounter)).toBe(true);
});

test("the badge counts a channel once, however many messages it holds", async () => {
    await startServer();
    await start();
    const store = getService("mail.store");
    const before = store.globalCounter;
    const thread = store["discuss.channel"].insert({
        id: 1,
        name: "chan",
        channel_type: "channel",
    });
    expect(store.globalCounter).toBe(before, {
        message: "a channel with nothing pending changes nothing",
    });
    thread.message_needaction_counter = 3;
    expect(store.globalCounter).toBe(before + 1);
});
