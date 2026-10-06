// @ts-check
import { defineMailModels, start, startServer } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { getService } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

/**
 * @param {any} store
 * @param {() => void} fn
 */
async function countTabMembershipComputes(store, fn) {
    const Model = store.Thread._rawStore.Models["discuss.channel"];
    const compute = Model._.fieldsCompute.get("messagingMenuTabs");
    let runs = 0;
    Model._.fieldsCompute.set("messagingMenuTabs", function () {
        runs++;
        return compute.call(this);
    });
    try {
        await fn();
    } finally {
        Model._.fieldsCompute.set("messagingMenuTabs", compute);
    }
    return runs;
}

test("inserting channels only computes the tabs of those channels", async () => {
    await startServer();
    await start();
    const store = getService("mail.store");
    for (let i = 1; i <= 50; i++) {
        store["discuss.channel"].insert({
            id: i,
            name: `chan ${i}`,
            channel_type: "channel",
        });
    }
    const channelTab = store.messagingMenu.channelTab;
    const before = channelTab.channels.length;
    const runs = await countTabMembershipComputes(store, () => {
        for (let i = 51; i <= 60; i++) {
            store["discuss.channel"].insert({
                id: i,
                name: `chan ${i}`,
                channel_type: "channel",
            });
        }
    });
    expect(runs).toBeLessThan(11, {
        message: "the 50 existing channels must not recompute their tab membership",
    });
    expect(channelTab.channels).toHaveLength(before);
});

test("a channel becoming pinned enters its tab, and unpinning removes it", async () => {
    await startServer();
    await start();
    const store = getService("mail.store");
    const channel = store["discuss.channel"].insert({
        id: 1,
        name: "chan",
        channel_type: "channel",
    });
    const channelTab = store.messagingMenu.channelTab;
    expect(channel.notIn(channelTab.channels)).toBe(true);
    channel.isLocallyPinned = true;
    expect(channel.in(channelTab.channels)).toBe(true);
    expect(channel.notIn(store.messagingMenu.chatTab.channels)).toBe(true);
    channel.isLocallyPinned = false;
    expect(channel.notIn(channelTab.channels)).toBe(true);
});
